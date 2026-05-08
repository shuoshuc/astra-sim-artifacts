#!/bin/bash
set -e

# Path
SCRIPT_DIR=$(dirname "$(realpath $0)")
# examples folder should be parallel to astra-sim and other folders.
# BASE_DIR is the /app folder in the provided docker container.
BASE_DIR=${SCRIPT_DIR}/../../
STG_DIR=${BASE_DIR}/STG
ASTRA_SIM=${BASE_DIR}/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Reconfigurable
TOOLS_PATH=${BASE_DIR}/tools
TRACE_PATH=${SCRIPT_DIR}/trace
INPUT_PATH=${SCRIPT_DIR}/inputs

# Fluid-model scenario: J0 alone on a 2x2x1 cluster. The X-dim contention
# from J1 (in the original 4x2 torus) is folded into asymmetric link
# parameters: X-links have halved BW (25 GB/s) and doubled latency (1000 ns)
# vs Y-links (50 GB/s, 500 ns). Schedule files are committed under inputs/.
TORUS_X_SIZE=2
TORUS_Y_SIZE=2
TORUS_Z_SIZE=1
MAIN_JOBS="2x2x1"
BG_JOBS="1x1x1"
DUMMY=false
NCORE=$(( $(nproc) - 2 ))
if [ "${NCORE}" -lt 1 ]; then NCORE=1; fi

# [Step 1] Prepare jobspec with the single main job (no background jobs; cluster is fully filled).
python ${TOOLS_PATH}/create_jobspec.py -D "${TORUS_X_SIZE}x${TORUS_Y_SIZE}x${TORUS_Z_SIZE}" \
    -J "${MAIN_JOBS}" -o "${INPUT_PATH}/jobspec.txt" -b "${BG_JOBS}"

# [Step 2] Generate traces using STG.
cd ${STG_DIR}
export STG_DIR TRACE_PATH DUMMY
parallel --jobs ${NCORE} --colsep ',' '
    if [[ ${DUMMY} == true && "{2}" == "B" ]]; then
        echo "{1} {2} should use tracegen_manual"
    else
        mkdir -p "${TRACE_PATH}/{1}"
        python "${STG_DIR}/main.py" --output_dir "${TRACE_PATH}/{1}" --output_name "{1}" \
            --model_type "dense" --dp "{3}" --tp "{4}" --pp "{5}" \
            --dmodel 32768 --dff 114688 --batch 128 --seq 2048 --dvocal 128000 \
            --head 128 --kvhead 16 --num_stacks 96 \
            --weight_sharded 0 --chakra_schema_version "v0.0.4"
    fi
' :::: "${INPUT_PATH}/jobspec.txt"

# [Step 3] Merge traces using the committed placement.json (no place.py — placement is fixed).
cd ${SCRIPT_DIR}
mkdir -p ${TRACE_PATH}/merged
TRACES=$(cut -d, -f1 "${INPUT_PATH}/jobspec.txt" | paste -sd, -)
python ${TOOLS_PATH}/merge_trace.py -i ${TRACE_PATH} --traces ${TRACES} -o ${TRACE_PATH}/merged/ -p ${INPUT_PATH}/placement.json

# [Step 4] Run ASTRA-sim with the committed asymmetric BW/latency schedules.
ulimit -n 65536
(
${ASTRA_SIM} \
    --workload-configuration=${TRACE_PATH}/merged/trace \
    --comm-group-configuration=${TRACE_PATH}/merged/comm_group.json \
    --system-configuration=${INPUT_PATH}/sys.json \
    --network-configuration=${INPUT_PATH}/network.yml \
    --remote-memory-configuration=${INPUT_PATH}/RemoteMemory.json \
    --bw-schedule=${INPUT_PATH}/bw_schedule.txt \
    --latency-schedule=${INPUT_PATH}/latency_schedule.txt \
    --npus-per-dim=${TORUS_X_SIZE},${TORUS_Y_SIZE},${TORUS_Z_SIZE}
)

# [Step 5] Extract JCT into a csv file.
python ${TOOLS_PATH}/extract_jct.py -p ${INPUT_PATH}/placement.json -l ${SCRIPT_DIR}/log/jct.log -o ${SCRIPT_DIR}/jct.csv
