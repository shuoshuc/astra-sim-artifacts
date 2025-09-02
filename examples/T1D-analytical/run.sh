#!/bin/bash
set -e

# Path
SCRIPT_DIR=$(dirname "$(realpath $0)")
# examples folder should be parallel to astra-sim and other folders.
# BASE_DIR is the /app folder in the provided docker container.
BASE_DIR=${SCRIPT_DIR}/../../
ASTRA_SIM=${BASE_DIR}/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware

# Run ASTRA-sim
(
${ASTRA_SIM} \
    --workload-configuration=${SCRIPT_DIR}/trace/trace \
    --system-configuration=${SCRIPT_DIR}/inputs/sys.json \
    --network-configuration=${SCRIPT_DIR}/inputs/network.yml \
    --comm-group-configuration=${SCRIPT_DIR}/inputs/comm_group.json \
    --remote-memory-configuration=${SCRIPT_DIR}/inputs/RemoteMemory.json
)
