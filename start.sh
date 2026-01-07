#!/bin/bash

POLICY=$1
MAIN_JOBS=$2

mkdir -p output
sudo docker run --ipc=host \
    -v $(pwd)/examples:/app/examples \
    -v $(pwd)/tools:/app/tools \
    astra /bin/bash -c "/app/examples/multitenant-reconfig/run.sh ${POLICY} ${MAIN_JOBS}"
mv $(pwd)/examples/multitenant-reconfig/jct.csv output
cd $(pwd)/examples/multitenant-reconfig
sudo rm -r tmp log trace inputs/jobspec.txt inputs/placement.json inputs/schedule.txt