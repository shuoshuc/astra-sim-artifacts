## Use Ubuntu
FROM ubuntu:22.04


### ================== System Setups ======================
## Install System Dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt -y update
RUN apt -y upgrade
RUN apt -y install \
    coreutils wget vim git \
    gcc g++ clang-format \
    make cmake \
    libboost-dev libboost-program-options-dev \
    openmpi-bin openmpi-doc libopenmpi-dev \
    python3 python3-pip python3-venv \
    graphviz

## Create Python venv: Required for Python 3.10
RUN python3 -m venv /opt/venv/astra-sim
ENV PATH="/opt/venv/astra-sim/bin:$PATH"
RUN pip3 install --upgrade pip
### ======================================================


### ====== Abseil Installation: Protobuf Dependency ======
## Download Abseil 20240722.0
WORKDIR /opt
RUN wget https://github.com/abseil/abseil-cpp/releases/download/20240722.0/abseil-cpp-20240722.0.tar.gz
RUN tar -xf abseil-cpp-20240722.0.tar.gz
RUN rm abseil-cpp-20240722.0.tar.gz

## Compile Abseil
WORKDIR /opt/abseil-cpp-20240722.0/build
RUN cmake .. \
    -DCMAKE_CXX_STANDARD=14 \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="/opt/abseil-cpp-20240722.0/install"
RUN cmake --build . --target install --config Release --parallel $(nproc)
ENV absl_DIR="/opt/abseil-cpp-20240722.0/install"
### ======================================================


### ============= Protobuf Installation ==================
## Download Protobuf 28.3 (=v5.28.3)
WORKDIR /opt
RUN wget https://github.com/protocolbuffers/protobuf/releases/download/v28.3/protobuf-28.3.tar.gz
RUN tar -xf protobuf-28.3.tar.gz
RUN rm protobuf-28.3.tar.gz

## Compile Protobuf
WORKDIR /opt/protobuf-28.3/build
RUN cmake .. \
    -DCMAKE_CXX_STANDARD=14 \
    -DCMAKE_BUILD_TYPE=Release \
    -Dprotobuf_BUILD_TESTS=OFF \
    -Dprotobuf_ABSL_PROVIDER=package \
    -DCMAKE_INSTALL_PREFIX="/opt/protobuf-28.3/install"
RUN cmake --build . --target install --config Release --parallel $(nproc)
ENV PATH="/opt/protobuf-28.3/install/bin:$PATH"
ENV protobuf_DIR="/opt/protobuf-28.3/install"

# Also, install Python protobuf package
RUN pip3 install protobuf==5.28.3

# Refer to astra-sim/CMakeLists.txt
ENV PROTOBUF_FROM_SOURCE="True"
### ======================================================


### ============= Get source code ==================
WORKDIR /app
RUN git clone https://github.com/astra-sim/astra-sim.git
WORKDIR /app/astra-sim
RUN git checkout tags/tutorial-micro2024-ns3fix250204
RUN git submodule update --init --recursive
WORKDIR /app
RUN ln -s astra-sim/extern/graph_frontend/chakra .
RUN git clone https://github.com/facebookresearch/param.git
RUN git clone https://github.com/astra-sim/symbolic_tensor_graph
### ======================================================


### ============= Chakra Installation ==================
WORKDIR /app/chakra
RUN pip3 install .
RUN git config --global --add safe.directory /app/param
WORKDIR /app/param/et_replay
RUN git checkout 7b19f586dd8b267333114992833a0d7e0d601630
RUN pip3 install .
RUN pip3 install --upgrade protobuf
### ======================================================


### ============= Astra-sim Installation ==================
WORKDIR /app/astra-sim
RUN bash ./build/astra_analytical/build.sh
RUN bash ./build/astra_ns3/build.sh
### ======================================================


### ================== Finalize ==========================
## Move to the application directory
WORKDIR /app
### ======================================================
