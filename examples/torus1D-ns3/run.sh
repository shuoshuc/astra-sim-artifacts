#!/bin/bash
set -e

# Path
SCRIPT_DIR=$(dirname "$(realpath $0)")
# examples folder should be parallel to astra-sim and other folders.
# BASE_DIR is the /app folder in the provided docker container.
BASE_DIR=${SCRIPT_DIR}/../../
ASTRA_SIM_BUILD_DIR=${BASE_DIR}/astra-sim/extern/network_backend/ns-3/build/scratch/
ASTRA_SIM_SCRATCH_DIR=${BASE_DIR}/astra-sim/extern/network_backend/ns-3/scratch/
ASTRA_SIM=./ns3.42-AstraSimNetwork-default

# Run ASTRA-sim
(
cd ${ASTRA_SIM_BUILD_DIR}
touch ../../scratch/output/flow.txt
${ASTRA_SIM} \
    --workload-configuration=${SCRIPT_DIR}/allreduce_8/allreduce \
    --system-configuration=${SCRIPT_DIR}/inputs/Ring_sys.json \
    --remote-memory-configuration=${SCRIPT_DIR}/inputs/RemoteMemory.json \
    --logical-topology-configuration=${SCRIPT_DIR}/inputs/logical_8nodes_1D.json \
    --network-configuration=${ASTRA_SIM_SCRATCH_DIR}/config/config.txt \
)
