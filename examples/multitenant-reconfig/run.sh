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

# Configurations
TORUS_X_SIZE=16
TORUS_Y_SIZE=16
TORUS_Z_SIZE=16
BLOCK_DIMS="1x1x1"
BW=50
POLICY="firstfit"
NCORE=$(( $(nproc) - 2 ))
if [ "${NCORE}" -lt 1 ]; then NCORE=1; fi
MAIN_JOBS="2x2x2"
DUMMY=true

# [Step 1] Prepare jobspec with main jobs and background jobs.
python ${TOOLS_PATH}/create_jobspec.py -D "${TORUS_X_SIZE}x${TORUS_Y_SIZE}x${TORUS_Z_SIZE}" \
    -J "${MAIN_JOBS}" -o "${INPUT_PATH}/jobspec.txt" -b "1x1x1"

# [Step 2] Generate traces using STG (in parallel).
cd ${STG_DIR}
export STG_DIR TRACE_PATH DUMMY
parallel --jobs ${NCORE} --colsep ',' '
    if [[ ${DUMMY} == true && "{2}" == "B" ]]; then
        echo "{1} {2} should use tracegen_manual"
    else
        mkdir -p "${TRACE_PATH}/{1}"
        python "${STG_DIR}/main.py" --output_dir "${TRACE_PATH}/{1}" --output_name "{1}" \
            --model_type "dense" --dp "{3}" --tp "{4}" --pp "{5}" \
            --weight_sharded 0 --chakra_schema_version "v0.0.4"
    fi
' :::: "${INPUT_PATH}/jobspec.txt"
# Handle background job generation.
python ${TOOLS_PATH}/tracegen_manual.py -J "${INPUT_PATH}/jobspec.txt" \
    -o "${TRACE_PATH}"

# [Step 3] (only for topomatch) Build traffic matrices for the traces.
if [[ ${POLICY} == "topomatch" ]]; then
    cd ${SCRIPT_DIR}
    export TOOLS_PATH TRACE_PATH
    parallel --jobs ${NCORE} --colsep ',' '
        python ${TOOLS_PATH}/topomatch_prep.py -f "${TRACE_PATH}/{1}" -m "${TRACE_PATH}/{1}/traffic.mat"
    ' :::: "${INPUT_PATH}/jobspec.txt"
fi

# [Step 4] Generate placement for multi-tenant scenarios.
python ${TOOLS_PATH}/place.py -D "${TORUS_X_SIZE}x${TORUS_Y_SIZE}x${TORUS_Z_SIZE}" \
    -B ${BLOCK_DIMS} -J "${INPUT_PATH}/jobspec.txt" -o ${INPUT_PATH}/placement.json \
    -P ${POLICY} -T ${TRACE_PATH}

# [Step 5] Merge traces for multi-tenant scenarios.
cd ${SCRIPT_DIR}
mkdir -p ${TRACE_PATH}/merged
TRACES=$(cut -d, -f1 "${INPUT_PATH}/jobspec.txt" | paste -sd, -)
python ${TOOLS_PATH}/merge_trace.py -i ${TRACE_PATH} --traces ${TRACES} -o ${TRACE_PATH}/merged/ -p ${INPUT_PATH}/placement.json

# [Step 6] Generate BW matrix for torus. Update bandwidth (bw) and npu count in the network config.
NPUS=$((TORUS_X_SIZE * TORUS_Y_SIZE * TORUS_Z_SIZE))
python ${TOOLS_PATH}/gen_bw_matrix.py -x ${TORUS_X_SIZE} -y ${TORUS_Y_SIZE} -z ${TORUS_Z_SIZE} -bw ${BW} -o ${INPUT_PATH}/schedule.txt
sed -i "s/npus_count: \[ .* \]/npus_count: [ ${NPUS} ]/" ${INPUT_PATH}/network.yml
sed -i "s/bandwidth: \[ .* \]/bandwidth: [ ${BW} ]/" ${INPUT_PATH}/network.yml

# [Step 7] Run ASTRA-sim
(
${ASTRA_SIM} \
    --workload-configuration=${TRACE_PATH}/merged/trace \
    --comm-group-configuration=${TRACE_PATH}/merged/comm_group.json \
    --system-configuration=${INPUT_PATH}/sys.json \
    --network-configuration=${INPUT_PATH}/network.yml \
    --remote-memory-configuration=${INPUT_PATH}/RemoteMemory.json \
    --circuit-schedules=${INPUT_PATH}/schedule.txt
)

# [Step 8] Extract JCT into a csv file.
python ${TOOLS_PATH}/extract_jct.py -p ${INPUT_PATH}/placement.json -l ${SCRIPT_DIR}/log/jct.log -o ${SCRIPT_DIR}/jct.csv