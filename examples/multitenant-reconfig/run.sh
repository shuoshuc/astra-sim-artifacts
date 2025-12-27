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
TORUS_X_SIZE=4
TORUS_Y_SIZE=2
TORUS_Z_SIZE=2
BLOCK_SIZE=1
BW=50
JOB_NAMES=()
JOB_SHAPES=""

# [Step 1] Prepare jobspec with main jobs and background jobs.
python ${TOOLS_PATH}/create_jobspec.py -D "${TORUS_X_SIZE}x${TORUS_Y_SIZE}x${TORUS_Z_SIZE}" \
    -J "2x2x2,2x2x1" -o "${INPUT_PATH}/jobspec.txt"

# [Step 2] Generate traces using STG
cd ${STG_DIR}
while IFS="," read -r JOB DP TP PP || [[ -n "$JOB" ]]; do
    mkdir -p ${TRACE_PATH}/${JOB}
    python ${STG_DIR}/main.py --output_dir "${TRACE_PATH}/${JOB}" --output_name "${JOB}" \
        --model_type "dense" --dp ${DP} --tp ${TP} --pp ${PP} \
        --weight_sharded 0 --chakra_schema_version "v0.0.4"

    # Append to the list of job shapes for placement generation.
    JOB_NAMES+=("${JOB}")
    if [ -n "$JOB_SHAPES" ]; then
        JOB_SHAPES="${JOB_SHAPES},"
    fi
    JOB_SHAPES="${JOB_SHAPES}${JOB}:${DP}x${TP}x${PP}"
done < "${INPUT_PATH}/jobspec.txt"

# [Step 3] Generate placement for multi-tenant scenarios.
python ${TOOLS_PATH}/place.py -D "${TORUS_X_SIZE}x${TORUS_Y_SIZE}x${TORUS_Z_SIZE}" \
    -B ${BLOCK_SIZE} -J ${JOB_SHAPES} -o ${INPUT_PATH}/placement.json

# [Step 4] Merge traces for multi-tenant scenarios.
cd ${SCRIPT_DIR}
mkdir -p ${TRACE_PATH}/merged
TRACES=$(IFS=, ; echo "${JOB_NAMES[*]}")
python ${TOOLS_PATH}/merge_trace.py -i ${TRACE_PATH} --traces ${TRACES} -o ${TRACE_PATH}/merged/ -p ${INPUT_PATH}/placement.json

# [Step 5] Generate BW matrix for torus. Update bandwidth (bw) and npu count in the network config.
NPUS=$((TORUS_X_SIZE * TORUS_Y_SIZE * TORUS_Z_SIZE))
python ${TOOLS_PATH}/gen_bw_matrix.py -x ${TORUS_X_SIZE} -y ${TORUS_Y_SIZE} -z ${TORUS_Z_SIZE} -bw ${BW} -o ${INPUT_PATH}/schedule.txt
sed -i "s/npus_count: \[ .* \]/npus_count: [ ${NPUS} ]/" ${INPUT_PATH}/network.yml
sed -i "s/bandwidth: \[ .* \]/bandwidth: [ ${BW} ]/" ${INPUT_PATH}/network.yml

# [Step 6] Run ASTRA-sim
(
${ASTRA_SIM} \
    --workload-configuration=${TRACE_PATH}/merged/trace \
    --comm-group-configuration=${TRACE_PATH}/merged/comm_group.json \
    --system-configuration=${INPUT_PATH}/sys.json \
    --network-configuration=${INPUT_PATH}/network.yml \
    --remote-memory-configuration=${INPUT_PATH}/RemoteMemory.json \
    --circuit-schedules=${INPUT_PATH}/schedule.txt
)

# [Step 7] Extract JCT into a csv file.
python ${TOOLS_PATH}/extract_jct.py -p ${INPUT_PATH}/placement.json -l ${SCRIPT_DIR}/log/jct.log -o ${SCRIPT_DIR}/jct.csv