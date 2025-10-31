#!/bin/bash
set -e

# Path
SCRIPT_DIR=$(dirname "$(realpath $0)")
# examples folder should be parallel to astra-sim and other folders.
# BASE_DIR is the /app folder in the provided docker container.
BASE_DIR=${SCRIPT_DIR}/../../
ASTRA_SIM=${BASE_DIR}/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware

# Merge traces
mkdir -p ${SCRIPT_DIR}/trace/merged
python ${BASE_DIR}/tools/merge_trace.py -i ${SCRIPT_DIR}/trace/ --traces J1,J0 -o ${SCRIPT_DIR}/trace/merged/ -p ${SCRIPT_DIR}/placement2.json

# Run ASTRA-sim
(
${ASTRA_SIM} \
    --workload-configuration=${SCRIPT_DIR}/trace/merged/trace \
    --comm-group-configuration=${SCRIPT_DIR}/trace/merged/comm_group.json \
    --system-configuration=${SCRIPT_DIR}/inputs/sys.json \
    --network-configuration=${SCRIPT_DIR}/inputs/network.yml \
    --remote-memory-configuration=${SCRIPT_DIR}/inputs/RemoteMemory.json
)
