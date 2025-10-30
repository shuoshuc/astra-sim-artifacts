#!/bin/bash
set -e

# =====================================================
# Usage:
#   ./run_stg.sh --output_dir <path> "J1 2 2 1" "J2 2 2 1" ...
#
# Example:
#   ./run_stg.sh --output_dir ./traces "J1 2 2 1" "J2 2 2 1"
#
# Purpose:
#   Generate N workloads (symbolic tensor graphs) for multitenant-T1D analytical examples.
#   Each job will be created in its own subfolder under the output_dir path.
# =====================================================

# parse args
if [[ "$1" != "--output_dir" || -z "$2" ]]; then
  echo "Usage: $0 --output_dir <path> \"J1 2 2 1\" \"J2 2 2 1\" ..."
  exit 1
fi

OUTPUT_BASE=$2
shift 2

if [[ $# -eq 0 ]]; then
  echo "Error: You must specify at least one job config (e.g., \"J1 2 2 1\")."
  exit 1
fi

JOBS=("$@")

# paths
SCRIPT_DIR=$(dirname "$(realpath "$0")")
BASE_DIR=${SCRIPT_DIR}/../
ASTRA_SIM_DIR=${BASE_DIR}/astra-sim
SYMBOLIC_TG_DIR=${ASTRA_SIM_DIR}/symbolic_tensor_graph

mkdir -p "${OUTPUT_BASE}"

# run stg
run_model() {
  local NAME=$1
  local DP=$2
  local TP=$3
  local PP=$4

  local OUTPUT_DIR="${OUTPUT_BASE}/${NAME}"

  # Default values
  local SP=1
  local EP=1
  local MICRO_BATCH=-1

  echo "-----------------------------------------"
  echo "Generating workload for ${NAME} (DP=${DP}, TP=${TP}, PP=${PP})"
  echo "Output: ${OUTPUT_DIR}"
  echo "-----------------------------------------"

  cd "${SYMBOLIC_TG_DIR}"
  python main.py \
    --output_dir "${OUTPUT_DIR}" \
    --output_name "${NAME}" \
    --model_type dense \
    --dp "${DP}" \
    --tp "${TP}" \
    --sp "${SP}" \
    --ep "${EP}" \
    --pp "${PP}" \
    --micro_batch "${MICRO_BATCH}" \
    --weight_sharded 0 \
    --chakra_schema_version v0.0.4
}

# run jobs
for job in "${JOBS[@]}"; do
  run_model $job
done

echo "All workloads saved to ${OUTPUT_BASE}"