#!/bin/bash
set -e

# start-fluid.sh — driver for the fluid-model experiment.
# Mounts host I/O folders and runs examples/fluid-model/run.sh inside the
# `astra` Docker image.

REPO_DIR=$(dirname "$(realpath "$0")")
CONFIGS_HOST="${REPO_DIR}/examples/fluid-model/inputs"

usage() {
    cat <<EOF
Usage: $0 <JOB_SHAPE> --input-dir DIR --output-dir DIR

Required:
  JOB_SHAPE         torus shape XxYxZ (e.g. 2x2x1)
  --input-dir DIR   host dir containing bw_schedule.txt and latency_schedule.txt
  --output-dir DIR  host dir that will receive jct.csv (created if missing)
EOF
    exit 2
}

# --- Parse CLI -------------------------------------------------------------

if [[ $# -lt 1 ]]; then usage; fi
JOB_SHAPE="$1"; shift

INPUT_DIR=""
OUTPUT_DIR=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --input-dir)  INPUT_DIR="$2"; shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        -h|--help)    usage ;;
        *)
            echo "start-fluid.sh: unknown argument: $1" >&2
            usage
            ;;
    esac
done

if [[ -z "${INPUT_DIR}" || -z "${OUTPUT_DIR}" ]]; then
    echo "start-fluid.sh: --input-dir and --output-dir are both required" >&2
    usage
fi

# --- Validate JOB_SHAPE ----------------------------------------------------

if [[ ! "${JOB_SHAPE}" =~ ^[0-9]+x[0-9]+x[0-9]+$ ]]; then
    echo "start-fluid.sh: JOB_SHAPE '${JOB_SHAPE}' is not in X x Y x Z form (e.g. 2x2x1)" >&2
    exit 1
fi

# --- Resolve and validate paths --------------------------------------------

if [[ ! -d "${INPUT_DIR}" ]]; then
    echo "start-fluid.sh: --input-dir '${INPUT_DIR}' is not a directory" >&2
    exit 1
fi
INPUT_DIR=$(realpath "${INPUT_DIR}")

if [[ ! -f "${INPUT_DIR}/bw_schedule.txt" ]]; then
    echo "start-fluid.sh: ${INPUT_DIR}/bw_schedule.txt is missing" >&2
    exit 1
fi
if [[ ! -f "${INPUT_DIR}/latency_schedule.txt" ]]; then
    echo "start-fluid.sh: ${INPUT_DIR}/latency_schedule.txt is missing" >&2
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"
OUTPUT_DIR=$(realpath "${OUTPUT_DIR}")

if [[ ! -d "${CONFIGS_HOST}" ]]; then
    echo "start-fluid.sh: configs dir ${CONFIGS_HOST} not found (run from repo root?)" >&2
    exit 1
fi

# --- Run container --------------------------------------------------------

sudo docker run --rm --ipc=host --ulimit nofile=65536:65536 \
    -v "${REPO_DIR}/examples":/app/examples:ro \
    -v "${REPO_DIR}/tools":/app/tools:ro \
    -v "${CONFIGS_HOST}":/app/configs:ro \
    -v "${INPUT_DIR}":/app/inputs:ro \
    -v "${OUTPUT_DIR}":/app/output \
    astra /bin/bash /app/examples/fluid-model/run.sh "${JOB_SHAPE}"
