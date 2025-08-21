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
