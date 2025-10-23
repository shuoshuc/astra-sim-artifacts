#!/bin/bash

# configure these values
DP=2
TP=2
PP=1
OUTPUT_NAME="denseB"
OUTPUT_DIR="/app/examples/multitenancy/inputs/${OUTPUT_NAME}"

# default values
SP=1
EP=1
BATCH=4
MICRO_BATCH=-1
SEQ=8
DMODEL=32
DFF=64
HEAD=1
KVHEAD=1
NUM_STACKS=1
VOCAB=32

cd /app/astra-sim/symbolic_tensor_graph || exit 1
python main.py \
  --output_dir "${OUTPUT_DIR}" \
  --output_name "${OUTPUT_NAME}" \
  --model_type dense \
  --dp "${DP}" \
  --tp "${TP}" \
  --sp "${SP}" \
  --ep "${EP}" \
  --pp "${PP}" \
  --batch "${BATCH}" \
  --micro_batch "${MICRO_BATCH}" \
  --seq "${SEQ}" \
  --dmodel "${DMODEL}" \
  --dff "${DFF}" \
  --head "${HEAD}" \
  --kvhead "${KVHEAD}" \
  --num_stacks "${NUM_STACKS}" \
  --dvocal "${VOCAB}"
