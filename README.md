This repo contains the scripts, example traces, configs required to run astra-sim experiments.

# Build docker container
Run this command to build a docker container with astra-sim and its dependencies installed.
```bash
docker build -t astra .
```

# Run an example experiment
Next, you can start the docker container and run a small 8-node allreduce experiment on a 1D torus.
To start the container, execute
```bash
docker run -it -v $(pwd)/examples:/app/examples astra
```

Inside the container, go to the example folder and run the script:
```bash
cd examples/T1D-ns3
./run.sh
```

# Tools
The tools/ folder contains useful tools to help with the experiments.

## Build torus
For example, build\_torus.py can construct a physical torus network given specified parameters.
```bash
python3 tools/build_torus.py --dims 4 4 -b 400Gbps -l 0.001ms -o physical_16nodes_2D.txt
```

## Generate STG traces
To generate traces using STG, make sure STG is installed in the docker container (e.g., at /app/STG).
Running the following command in the docker container creates a 4-XPU trace called workload.[0-3].et
```bash
cd /app/STG && mkdir -p tmp_trace && python3 main.py --output_dir ./tmp_trace --output_name "workload" --model_type "dense" --dp 2 --tp 2 --pp 1 --weight_sharded 0 --chakra_schema_version "v0.0.4"
```

## Merge traces
To merge multiple traces in a multi-tenant experiment, use merge\_trace.py.
```bash
python merge_trace.py -i /app/examples/multitenant-T1D-analytical/trace/ --traces J1,J0 -o ./tmp/ -p /app/examples/multitenant-T1D-analytical/placement.json
```

## Place jobs
To place jobs onto the torus, either maintaining the job shape or randomly (with an extra -r), use place.py
```bash
python tools/place.py -N 4 -B 2 -J J0:4x4x2,J1:4x4x2
```