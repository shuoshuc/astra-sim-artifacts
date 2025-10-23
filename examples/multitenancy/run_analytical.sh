#!/bin/bash
set -e

# path to astra-sim
PROJECT_DIR="/app/astra-sim"
EXAMPLE_DIR="${PROJECT_DIR:?}/examples"

# ============= configure me
ASTRA_SIM="${PROJECT_DIR:?}/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Aware"
WORKLOAD="/app/examples/multitenancy/inputs/mergedAB/mergedAB"
COMM_GROUP="/app/examples/multitenancy/inputs/mergedAB/mergedAB.json"
SYSTEM="/app/examples/multitenancy/configs/system/torus_tpu4_1d.json"
NETWORK="/app/examples/multitenancy/configs/network/ring_1d_8nodes.yml"
REMOTE_MEMORY="${EXAMPLE_DIR:?}/remote_memory/analytical/no_memory_expansion.json"
# =============


# start
echo "[ASTRA-sim] Compiling ASTRA-sim with the Analytical Network Backend..."
echo ""

# Compile
"${PROJECT_DIR:?}"/build/astra_analytical/build.sh

echo ""
echo "[ASTRA-sim] Compilation finished."
echo "[ASTRA-sim] Running ASTRA-sim Example with Analytical Network Backend..."
echo ""

# run ASTRA-sim
"${ASTRA_SIM:?}" \
    --workload-configuration="${WORKLOAD}" \
    --system-configuration="${SYSTEM:?}" \
    --remote-memory-configuration="${REMOTE_MEMORY:?}" \
    --network-configuration="${NETWORK:?}" \
    --comm-group-configuration="${COMM_GROUP:?}"

# finalize
echo ""
echo "[ASTRA-sim] Finished the execution."
