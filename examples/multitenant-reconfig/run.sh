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
TRACE_PATH=${SCRIPT_DIR}/trace/merged/

# TODO: Merge traces for multi-tenant scenarios.
mkdir -p ${TRACE_PATH}
cd ${STG_DIR}
python3 ${STG_DIR}/main.py --output_dir ${TRACE_PATH} --output_name "trace" \
    --model_type "dense" --dp 2 --tp 2 --pp 1 \
    --weight_sharded 0 --chakra_schema_version "v0.0.4"

# Generate BW matrix. Make sure bandwidth (bw) is consistent with the network config.
python3 ${BW_GEN} -x 2 -y 2 -z 1 -bw 50 -o ${SCRIPT_DIR}/inputs/schedule.txt

# Run ASTRA-sim
(
${ASTRA_SIM} \
    --workload-configuration=${SCRIPT_DIR}/trace/merged/trace \
    --comm-group-configuration=${SCRIPT_DIR}/trace/merged/trace.json \
    --system-configuration=${SCRIPT_DIR}/inputs/sys.json \
    --network-configuration=${SCRIPT_DIR}/inputs/network.yml \
    --remote-memory-configuration=${SCRIPT_DIR}/inputs/RemoteMemory.json \
    --circuit-schedules=${SCRIPT_DIR}/inputs/schedule.txt
)
