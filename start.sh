#!/bin/bash

POLICY=${1:-"firstfit"}
MAIN_JOBS=${2:-"2x2x2"}
TORUS_X_SIZE=${3:-16}
TORUS_Y_SIZE=${4:-16}
TORUS_Z_SIZE=${5:-16}
BW=${6:-50}
BG_JOBS=${7:-"1x1x1"}
DUMMY=${8:-true}

mkdir -p output
sudo docker run --ipc=host \
    -v $(pwd)/examples:/app/examples \
    -v $(pwd)/tools:/app/tools \
    astra /bin/bash -c "/app/examples/multitenant-reconfig/run.sh \
        ${POLICY} \
        ${MAIN_JOBS} \
        ${TORUS_X_SIZE} \
        ${TORUS_Y_SIZE} \
        ${TORUS_Z_SIZE} \
        ${BW} \
        ${BG_JOBS} \
        ${DUMMY}"
mv $(pwd)/examples/multitenant-reconfig/jct.csv output
cd $(pwd)/examples/multitenant-reconfig
sudo rm -r log trace inputs/jobspec.txt inputs/placement.json inputs/schedule.txt
