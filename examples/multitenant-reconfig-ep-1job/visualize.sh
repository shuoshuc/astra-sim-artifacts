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

# chakra_visualizer \
#     --input_filename ${TRACE_PATH}/merged/trace.3.et \
#     --output_filename visualize_j0_0.dot


chakra_jsonizer \
    --input_filename ${TRACE_PATH}/merged/trace.5.et \
    --output_filename j1_0.json


# https://github.com/mlcommons/chakra/blob/main/USER_GUIDE.md

