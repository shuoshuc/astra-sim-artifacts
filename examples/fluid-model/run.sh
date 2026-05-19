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

# Single job that fills the entire cluster. Job shape == torus shape ==
# DP x TP x PP. Per-dim BW/latency model asymmetric link parameters (e.g.,
# X-links contended by a notional other tenant -> halved BW, doubled latency).
JOB_SHAPE=${1:-"2x2x1"}
BW_PER_DIM=${2:-"25,50,50"}    # GB/s, X,Y,Z
LT_PER_DIM=${3:-"1000,500,500"} # ns,  X,Y,Z

IFS='x' read -r TORUS_X_SIZE TORUS_Y_SIZE TORUS_Z_SIZE <<< "${JOB_SHAPE}"
NPUS=$((TORUS_X_SIZE * TORUS_Y_SIZE * TORUS_Z_SIZE))

mkdir -p "${INPUT_PATH}" "${TRACE_PATH}"

# [Step 1] Emit a one-line jobspec for the single main job (no create_jobspec.py).
echo "J0,M,${TORUS_X_SIZE},${TORUS_Y_SIZE},${TORUS_Z_SIZE}" > "${INPUT_PATH}/jobspec.txt"

# [Step 2] Generate the trace with STG (single invocation, no parallel).
mkdir -p "${TRACE_PATH}/J0"
cd ${STG_DIR}
python "${STG_DIR}/main.py" --output_dir "${TRACE_PATH}/J0" --output_name "J0" \
    --model_type "dense" \
    --dp "${TORUS_X_SIZE}" --tp "${TORUS_Y_SIZE}" --pp "${TORUS_Z_SIZE}" \
    --dmodel 32768 --dff 114688 --batch 128 --seq 2048 --dvocal 128000 \
    --head 128 --kvhead 16 --num_stacks 96 \
    --weight_sharded 0 --chakra_schema_version "v0.0.4"

# [Step 3] Emit identity placement (logical == physical; no place.py).
python -c "
import json
N = ${TORUS_X_SIZE} * ${TORUS_Y_SIZE} * ${TORUS_Z_SIZE}
with open('${INPUT_PATH}/placement.json', 'w') as f:
    json.dump({f'J0-{i}': i for i in range(N)}, f, indent=4)
    f.write('\n')
"

# [Step 4] Merge traces + generate BW/LT schedules + patch network.yml.
cd ${SCRIPT_DIR}
mkdir -p ${TRACE_PATH}/merged
python ${TOOLS_PATH}/merge_trace.py -i ${TRACE_PATH} --traces "J0" \
    -o ${TRACE_PATH}/merged/ -p ${INPUT_PATH}/placement.json

python ${TOOLS_PATH}/gen_schedule.py \
    -x ${TORUS_X_SIZE} -y ${TORUS_Y_SIZE} -z ${TORUS_Z_SIZE} \
    -bw "${BW_PER_DIM}" -lt "${LT_PER_DIM}" \
    --bw-output ${INPUT_PATH}/bw_schedule.txt \
    --latency-output ${INPUT_PATH}/latency_schedule.txt

# network.yml's bandwidth/latency are scalar fallbacks; the matrix files
# above override them. Patch the YAML with the first-dim values just to
# keep the file internally consistent.
BW_FIRST=$(echo "${BW_PER_DIM}" | cut -d, -f1)
LT_FIRST=$(echo "${LT_PER_DIM}" | cut -d, -f1)
sed -i "s/npus_count: \[ .* \]/npus_count: [ ${NPUS} ]/" ${INPUT_PATH}/network.yml
sed -i "s/bandwidth: \[ .* \]/bandwidth: [ ${BW_FIRST} ]/" ${INPUT_PATH}/network.yml
sed -i "s/latency: \[ .* \]/latency: [ ${LT_FIRST} ]/" ${INPUT_PATH}/network.yml

# [Step 5] Run ASTRA-sim, then extract JCT.
# Raise the open-file limit: each Sys keeps trace.{rank}.et open for the
# run's lifetime; the default soft limit of 1024 is insufficient at scale.
# Note: the simulator writes log/jct.log itself (trace-level only) via a
# dedicated spdlog sink rooted at the CWD's "log/" folder; do NOT tee
# stdout to that path or extract_jct.py will choke on info-level lines.
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

python ${TOOLS_PATH}/extract_jct.py -p ${INPUT_PATH}/placement.json \
    -l ${SCRIPT_DIR}/log/jct.log -o ${SCRIPT_DIR}/jct.csv
