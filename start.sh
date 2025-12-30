#!/bin/bash

mkdir -p output
sudo docker run --ipc=host -v $(pwd)/examples:/app/examples -v $(pwd)/tools:/app/tools astra /bin/bash -c /app/examples/multitenant-reconfig/run.sh
mv $(pwd)/examples/multitenant-reconfig/jct.csv output
cd $(pwd)/examples/multitenant-reconfig
sudo rm -r log trace inputs/jobspec.txt inputs/placement.json inputs/schedule.txt