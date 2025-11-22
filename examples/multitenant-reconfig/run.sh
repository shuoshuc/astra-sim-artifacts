#!/bin/bash
set -e

# Path
SCRIPT_DIR=$(dirname "$(realpath $0)")
# examples folder should be parallel to astra-sim and other folders.
# BASE_DIR is the /app folder in the provided docker container.
BASE_DIR=${SCRIPT_DIR}/../../
STG_DIR=${BASE_DIR}/STG
ASTRA_SIM=${BASE_DIR}/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Reconfigurable
BW_GEN=${BASE_DIR}/tools/gen_bw_matrix.py
MERGE_TRACE=${BASE_DIR}/tools/merge_trace.py
TRACE_PATH=${SCRIPT_DIR}/trace

# Generate two traces using STG
cd ${STG_DIR}
mkdir -p ${TRACE_PATH}/J0
python3 ${STG_DIR}/main.py --output_dir "${TRACE_PATH}/J0" --output_name "J0" \
    --model_type "dense" --dp 4 --tp 2 --pp 4 \
    --weight_sharded 0 --chakra_schema_version "v0.0.4"
mkdir -p ${TRACE_PATH}/J1
python3 ${STG_DIR}/main.py --output_dir "${TRACE_PATH}/J1" --output_name "J1" \
    --model_type "dense" --dp 4 --tp 2 --pp 4 \
    --weight_sharded 0 --chakra_schema_version "v0.0.4"

# Merge traces for multi-tenant scenarios.
cd ${SCRIPT_DIR}
mkdir -p ${TRACE_PATH}/merged
python ${MERGE_TRACE} -i ${TRACE_PATH} --traces J0,J1 -o ${TRACE_PATH}/merged/ -p ${SCRIPT_DIR}/inputs/placement.json

# Generate BW matrix. Make sure bandwidth (bw) is consistent with the network config.
python3 ${BW_GEN} -x 4 -y 4 -z 4 -bw 50 -o ${SCRIPT_DIR}/inputs/schedule.txt

# Run ASTRA-sim
(
${ASTRA_SIM} \
    --workload-configuration=${SCRIPT_DIR}/trace/merged/trace \
    --comm-group-configuration=${SCRIPT_DIR}/trace/merged/comm_group.json \
    --system-configuration=${SCRIPT_DIR}/inputs/sys.json \
    --network-configuration=${SCRIPT_DIR}/inputs/network.yml \
    --remote-memory-configuration=${SCRIPT_DIR}/inputs/RemoteMemory.json \
    --circuit-schedules=${SCRIPT_DIR}/inputs/schedule.txt
)