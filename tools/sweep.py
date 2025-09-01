import yaml
import subprocess
import math
import concurrent.futures
import itertools
import os
import json
import re
import csv
from sys import stdout
from build_torus import generate_torus_links, model_contention


def extract_cycles(log_string: str) -> int | None:
    """
    Extracts the first cycle count number from a log string.

    Args:
        log_string: The multi-line string containing log output.

    Returns:
        The extracted cycle number as an integer, or None if not found.
    """
    pattern = r"finished, (\d+) cycles"
    match = re.search(pattern, log_string)
    if match:
        return int(match.group(1))

    return None


def run_helper(coll_size: str, use_ns3: bool):
    BASE_DIR = "/app"
    TRACE_DIR = os.path.normpath(
        os.path.join(BASE_DIR, f"examples/sweep/allreduce_{coll_size}")
    )
    INPUT_DIR = os.path.normpath(os.path.join(BASE_DIR, "examples/sweep/inputs"))
    NS3_BIN = "astra-sim/extern/network_backend/ns-3/build/scratch/ns3.42-AstraSimNetwork-default"
    ANALYTICAL_BIN = "astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware"

    if use_ns3:
        astra_sim_bin = os.path.normpath(os.path.join(BASE_DIR, NS3_BIN))
    else:
        astra_sim_bin = os.path.normpath(os.path.join(BASE_DIR, ANALYTICAL_BIN))
    cmd = (
        f"{astra_sim_bin} "
        f"--workload-configuration={TRACE_DIR}/trace "
        f"--remote-memory-configuration={INPUT_DIR}/RemoteMemory.json "
        f"--system-configuration={INPUT_DIR}/sys.json "
        f"--comm-group-configuration={INPUT_DIR}/comm_group.json "
    )
    if use_ns3:
        cmd += (
            f"--logical-topology-configuration={INPUT_DIR}/logical_network.json "
            f"--network-configuration={INPUT_DIR}/ns3_config.txt"
        )
    else:
        cmd += f"--network-configuration={INPUT_DIR}/network.yml"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
    return result


def gen_comm_group(folder_path: str, ring_size: int):
    """
    Generates a communication group JSON file for the given ring size.
    The output format is: { "0": [0, 1, ..., ring_size-1] }
    Args:
        folder_path (str): The directory where the file will be created.
        ring_size (int): The size of the ring (number of nodes).
    """
    comm_group = {"0": list(range(ring_size))}
    file_path = os.path.join(folder_path, "comm_group.json")
    with open(file_path, "w") as f:
        json.dump(comm_group, f, indent=2)


def gen_network_config(
    folder_path: str,
    ring_size: int,
    bandwidth_Gbps: int,
    latency_ns: int,
    use_ns3: bool,
    N: int,
    M: int,
):
    """
    Generates a network config YAML file for the given ring size.
    Args:
        folder_path (str): The directory where the file will be created.
        ring_size (int): The size of the ring (number of NPUs).
        bandwidth_Gbps (int): The bandwidth for all links (in GB/s).
        latency_ns (int): The latency for all links (in nsec).
        use_ns3 (bool): Whether to use NS3 for simulation.
        N (int): Number of links to apply contention to.
        M (int): Number of jobs to divide bandwidth by.
    """
    if use_ns3:
        # Generate logical network config for ns-3.
        config = {"logical-dims": [str(ring_size)]}
        file_path = os.path.join(folder_path, "logical_network.json")
        with open(file_path, "w") as f:
            json.dump(config, f, indent=4)

        # Generate physical network config for ns-3.
        header_line1, header_line2, links = generate_torus_links(
            [ring_size], f"{bandwidth_Gbps}Gbps", f"{latency_ns / 1e6}ms"
        )
        contending_links = model_contention(links, n_links=N, m_jobs=M)
        file_path = os.path.join(folder_path, "physical_network.txt")
        with open(file_path, "w") as f:
            f.write(header_line1 + "\n")
            f.write(header_line2 + "\n")
            f.write(
                "\n".join(
                    sorted(contending_links, key=lambda l: tuple(map(int, l.split()[:2])))
                )
            )
    else:
        # Generate network config for analytical backend.
        config = {
            "topology": ["Ring"],
            "npus_count": [ring_size],
            "bandwidth": [bandwidth_Gbps / 8],
            "latency": [latency_ns],
        }
        file_path = os.path.join(folder_path, "network.yml")
        with open(file_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)


def sweep(use_ns3: bool):
    config_folder = "/app/examples/sweep/inputs"
    os.makedirs(config_folder, exist_ok=True)

    sweep_results = []

    ring_sizes = list(range(4, 33, 4)) + list(range(48, 257, 16))
    M_list = [2, 8]
    collective_sizes = ["1MB"]
    for size in ring_sizes:
        N_list = [1] + [2**i for i in range(1, int(math.log2(size // 2)) + 1)]
        base_cases = [(0, 1, coll_size) for coll_size in collective_sizes]
        for N, M, coll_size in base_cases + list(
            itertools.product(N_list, M_list, collective_sizes)
        ):
            gen_comm_group(folder_path=config_folder, ring_size=size)
            gen_network_config(
                folder_path=config_folder,
                ring_size=size,
                bandwidth_Gbps=400,
                latency_ns=1000,
                use_ns3=use_ns3,
                N=N,
                M=M,
            )
            result = run_helper(coll_size=coll_size, use_ns3=use_ns3)
            max_cycles = 0
            for line in result.stdout.splitlines():
                if "finished, " in line:
                    cycles = extract_cycles(line)
                    max_cycles = max(max_cycles, cycles if cycles is not None else 0)
            sweep_results.append((size, N, M, coll_size, max_cycles))
            print(
                f"Run S={size}, N={N}, M={M}, collective size={coll_size}: {max_cycles} cycles"
            )

    # Dump the sweep results to a CSV file
    header = [
        "ring size",
        "N contending links",
        "M contending jobs",
        "collective size",
        "cycles",
    ]
    filename = "sweep.csv"
    with open(filename, "w", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(header)
        csv_writer.writerows(sweep_results)


if __name__ == "__main__":
    sweep(use_ns3=True)
