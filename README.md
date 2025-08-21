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
cd examples/torus1D-ns3
./run.sh
```

# Tools
The tools/ folder contains useful tools to help with the experiments.

For example, build\_torus.py can construct a physical torus network given specified parameters.
```bash
python3 tools/build_torus.py --dims 4 4 -b 400Gbps -l 0.001ms -o physical_16nodes_2D.txt
```
