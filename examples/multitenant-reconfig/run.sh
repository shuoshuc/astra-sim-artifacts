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

# Generate two traces using STG
cd ${STG_DIR}
mkdir -p ${TRACE_PATH}/J0
python ${STG_DIR}/main.py --output_dir "${TRACE_PATH}/J0" --output_name "J0" \
    --model_type "dense" --dp 4 --tp 4 --pp 2 \
    --weight_sharded 0 --chakra_schema_version "v0.0.4"
mkdir -p ${TRACE_PATH}/J1
python ${STG_DIR}/main.py --output_dir "${TRACE_PATH}/J1" --output_name "J1" \
    --model_type "dense" --dp 4 --tp 4 --pp 2 \
    --weight_sharded 0 --chakra_schema_version "v0.0.4"

# Merge traces for multi-tenant scenarios.
cd ${SCRIPT_DIR}
mkdir -p ${TRACE_PATH}/merged
python ${TOOLS_PATH}/merge_trace.py -i ${TRACE_PATH} --traces J0,J1 -o ${TRACE_PATH}/merged/ -p ${INPUT_PATH}/placement.json

# Generate BW matrix for torus. Make sure bandwidth (bw) and npu count are consistent with the network config.
XSIZE=4
YSIZE=4
ZSIZE=4
BW=50
NPUS=$((XSIZE * YSIZE * ZSIZE))
python ${TOOLS_PATH}/gen_bw_matrix.py -x ${XSIZE} -y ${YSIZE} -z ${ZSIZE} -bw ${BW} -o ${INPUT_PATH}/schedule.txt
sed -i "s/npus_count: \[ .* \]/npus_count: [ ${NPUS} ]/" ${INPUT_PATH}/network.yml
sed -i "s/bandwidth: \[ .* \]/bandwidth: [ ${BW} ]/" ${INPUT_PATH}/network.yml

# Run ASTRA-sim
(
${ASTRA_SIM} \
    --workload-configuration=${TRACE_PATH}/merged/trace \
    --comm-group-configuration=${TRACE_PATH}/merged/comm_group.json \
    --system-configuration=${INPUT_PATH}/sys.json \
    --network-configuration=${INPUT_PATH}/network.yml \
    --remote-memory-configuration=${INPUT_PATH}/RemoteMemory.json \
    --circuit-schedules=${INPUT_PATH}/schedule.txt
)

# Extract JCT into a csv file.
python ${TOOLS_PATH}/extract_jct.py -p ${INPUT_PATH}/placement.json -l ${SCRIPT_DIR}/log/jct.log -o ${SCRIPT_DIR}/jct.csv