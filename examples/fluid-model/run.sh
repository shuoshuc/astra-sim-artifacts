#!/bin/bash
set -e

# fluid-model runner. Takes a single JOB_SHAPE argument and consumes
# pre-built bw_schedule.txt / latency_schedule.txt from /app/inputs.
# Outputs jct.csv to /app/output. All intermediates live under
# /tmp/fluid-model/ and disappear on container exit.

usage() {
    echo "Usage: $0 <JOB_SHAPE>"
    echo "  JOB_SHAPE: torus shape as XxYxZ (e.g. 2x2x1)"
    echo ""
    echo "Mounts (set by the wrapper script):"
    echo "  /app/configs  static inputs (sys.json, RemoteMemory.json, network.yml)"
    echo "  /app/inputs   user-supplied bw_schedule.txt, latency_schedule.txt"
    echo "  /app/output   destination for jct.csv"
    exit 2
}

if [[ $# -ne 1 ]]; then
    usage
fi

JOB_SHAPE="$1"

# In-container paths. Not user-overridable; the wrapper owns mount layout.
BASE_DIR=/app
STG_DIR=${BASE_DIR}/STG
ASTRA_SIM=${BASE_DIR}/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Reconfigurable
TOOLS_PATH=${BASE_DIR}/tools
CONFIGS_DIR=${BASE_DIR}/configs
INPUTS_DIR=${BASE_DIR}/inputs
OUTPUT_DIR=${BASE_DIR}/output
WORK_DIR=/tmp/fluid-model

BW_FILE=${INPUTS_DIR}/bw_schedule.txt
LT_FILE=${INPUTS_DIR}/latency_schedule.txt

# --- Parse JOB_SHAPE -------------------------------------------------------

if [[ ! "${JOB_SHAPE}" =~ ^[0-9]+x[0-9]+x[0-9]+$ ]]; then
    echo "run.sh: JOB_SHAPE '${JOB_SHAPE}' is not in X x Y x Z form (e.g. 2x2x1)" >&2
    exit 1
fi
IFS='x' read -r X Y Z <<< "${JOB_SHAPE}"
if [[ ${X} -lt 1 || ${Y} -lt 1 || ${Z} -lt 1 ]]; then
    echo "run.sh: JOB_SHAPE dims must all be >= 1 (got ${X}x${Y}x${Z})" >&2
    exit 1
fi
N=$((X * Y * Z))

# --- [Step 1] Validate schedule files --------------------------------------

validate_schedule() {
    local file="$1"
    local expected_tag="$2"
    if [[ ! -f "${file}" ]]; then
        echo "run.sh: ${file} does not exist" >&2
        exit 1
    fi
    # First-line tag check (first whitespace token).
    local first_tok
    first_tok=$(awk 'NR==1 {print $1; exit}' "${file}")
    if [[ "${first_tok}" != "${expected_tag}" ]]; then
        echo "run.sh: ${file}: expected first token '${expected_tag}', got '${first_tok}'" >&2
        exit 1
    fi
    # Last-line END terminator.
    local last_tok
    last_tok=$(awk 'END {print $1}' "${file}")
    if [[ "${last_tok}" != "END" ]]; then
        echo "run.sh: ${file}: expected last line to be 'END', got '${last_tok}'" >&2
        exit 1
    fi
    # Body: exactly N rows of N numeric fields each.
    local total
    total=$(awk 'END {print NR}' "${file}")
    local expected_total=$((N + 2))   # tag + N rows + END
    if [[ "${total}" -ne "${expected_total}" ]]; then
        echo "run.sh: ${file}: expected ${expected_total} lines (1 tag + ${N} rows + END) for JOB_SHAPE ${JOB_SHAPE}, found ${total}" >&2
        exit 1
    fi
    awk -v N="${N}" -v file="${file}" '
        NR > 1 && $1 != "END" {
            if (NF != N) {
                printf("run.sh: %s: row %d has %d fields, expected %d\n", file, NR-1, NF, N) > "/dev/stderr"
                exit 1
            }
            for (i = 1; i <= NF; i++) {
                if ($i !~ /^-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$/) {
                    printf("run.sh: %s: row %d field %d is not numeric: %s\n", file, NR-1, i, $i) > "/dev/stderr"
                    exit 1
                }
            }
        }
    ' "${file}"
}
validate_schedule "${BW_FILE}" "BW"
validate_schedule "${LT_FILE}" "LT"

# --- Prepare work dir ------------------------------------------------------

rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}/trace/J0" "${WORK_DIR}/log"

# --- [Step 2] Emit jobspec (single line, single job) -----------------------

echo "J0,M,${X},${Y},${Z}" > "${WORK_DIR}/jobspec.txt"

# --- [Step 3] Generate trace via STG ---------------------------------------

cd "${STG_DIR}"
python "${STG_DIR}/main.py" --output_dir "${WORK_DIR}/trace/J0" --output_name "J0" \
    --model_type "dense" \
    --dp "${X}" --tp "${Y}" --pp "${Z}" \
    --dmodel 32768 --dff 114688 --batch 128 --seq 2048 --dvocal 128000 \
    --head 128 --kvhead 16 --num_stacks 96 \
    --weight_sharded 0 --chakra_schema_version "v0.0.4"

# --- [Step 4] Identity placement -------------------------------------------

python -c "
import json
N = ${N}
with open('${WORK_DIR}/placement.json', 'w') as f:
    json.dump({f'J0-{i}': i for i in range(N)}, f, indent=4)
    f.write('\n')
"

# --- [Step 5] No merge --- STG output consumed directly --------------------
# Workload prefix => ${WORK_DIR}/trace/J0/J0  (simulator appends .{rank}.et)
# Comm group     => ${WORK_DIR}/trace/J0/J0.json

# --- [Step 6] Materialize patched network.yml ------------------------------

cp "${CONFIGS_DIR}/network.yml" "${WORK_DIR}/network.yml"

# First nonzero numeric entry in the matrix body, scanning row-major. Falls
# back to 0 if no nonzero entry exists.
first_nonzero() {
    local file="$1"
    awk '
        NR == 1 { next }                  # skip tag line
        $1 == "END" { exit }              # stop at terminator
        {
            for (i = 1; i <= NF; i++) {
                if ($i + 0 != 0) { print $i; found = 1; exit }
            }
        }
        END { if (!found) print "0" }
    ' "${file}"
}
BW_SCALAR=$(first_nonzero "${BW_FILE}")
LT_SCALAR=$(first_nonzero "${LT_FILE}")
: "${BW_SCALAR:=0}"
: "${LT_SCALAR:=0}"

sed -i "s/npus_count: \[ .* \]/npus_count: [ ${N} ]/" "${WORK_DIR}/network.yml"
sed -i "s/bandwidth: \[ .* \]/bandwidth: [ ${BW_SCALAR} ]/" "${WORK_DIR}/network.yml"
sed -i "s/latency: \[ .* \]/latency: [ ${LT_SCALAR} ]/" "${WORK_DIR}/network.yml"

# --- [Step 7] Run ASTRA-sim ------------------------------------------------
# Each Sys keeps trace.{rank}.et open for the run's lifetime; default 1024
# soft FD limit is insufficient at scale.
ulimit -n 65536

cd "${WORK_DIR}"
"${ASTRA_SIM}" \
    --workload-configuration="${WORK_DIR}/trace/J0/J0" \
    --comm-group-configuration="${WORK_DIR}/trace/J0/J0.json" \
    --system-configuration="${CONFIGS_DIR}/sys.json" \
    --network-configuration="${WORK_DIR}/network.yml" \
    --remote-memory-configuration="${CONFIGS_DIR}/RemoteMemory.json" \
    --bw-schedule="${BW_FILE}" \
    --latency-schedule="${LT_FILE}" \
    --npus-per-dim="${X},${Y},${Z}"

# --- [Step 8] Extract JCT --------------------------------------------------

mkdir -p "${OUTPUT_DIR}"
python "${TOOLS_PATH}/extract_jct.py" \
    -p "${WORK_DIR}/placement.json" \
    -l "${WORK_DIR}/log/jct.log" \
    -o "${OUTPUT_DIR}/jct.csv"

echo "run.sh: wrote ${OUTPUT_DIR}/jct.csv"
