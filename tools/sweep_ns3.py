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


def run_helper(coll_size: str, logical_filename: str):
    BASE_DIR = "/app"
    TRACE_DIR = os.path.normpath(
        os.path.join(BASE_DIR, f"examples/sweep-ns3/allreduce_{coll_size}")
    )
    INPUT_DIR = os.path.normpath(os.path.join(BASE_DIR, "examples/sweep-ns3/inputs"))
    ASTRA_SIM_BUILD_DIR = "astra-sim/extern/network_backend/ns-3/build/scratch/"
    ASTRA_SIM_BIN = "ns3.42-AstraSimNetwork-default"
    astra_sim_bin = os.path.normpath(
        os.path.join(BASE_DIR, ASTRA_SIM_BUILD_DIR, ASTRA_SIM_BIN)
    )
    cmd = (
        f"{astra_sim_bin} "
        f"--workload-configuration={TRACE_DIR}/trace "
        f"--system-configuration={INPUT_DIR}/Ring_sys.json "
        f"--remote-memory-configuration={INPUT_DIR}/RemoteMemory.json "
        f"--network-configuration={INPUT_DIR}/ns3_config.txt "
        f"--logical-topology-configuration={INPUT_DIR}/{logical_filename}"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
    return result


def gen_physical_config(
    folder_path: str,
    filename: str,
    ring_size: int,
    bandwidth: str = "400Gbps",
    latency: str = "0.001ms",
    n_links: int = 2,
    m_jobs: int = 4,
):
    """
    Generates a physical network config file in the specified folder using torus topology.
    Args:
        folder_path (str): The directory where the file will be created.
        filename (str): The name of the file to create.
        dims (list): The dimensions for the torus topology.
        bandwidth (str): The bandwidth for all links.
        latency (str): The latency for all links.
        n_links (int): Number of links to apply contention to.
        m_jobs (int): Number of jobs to divide bandwidth by.
    """
    header_line1, header_line2, links = generate_torus_links(
        [ring_size], bandwidth, latency
    )
    contending_links = model_contention(links, n_links=n_links, m_jobs=m_jobs)
    file_path = os.path.join(folder_path, filename)
    with open(file_path, "w") as f:
        f.write(header_line1 + "\n")
        f.write(header_line2 + "\n")
        f.write(
            "\n".join(
                sorted(contending_links, key=lambda l: tuple(map(int, l.split()[:2])))
            )
        )


def gen_logical_config(folder_path: str, filename: str, ring_size: int):
    """
    Generates a logical network config file in the specified folder.
    Args:
            folder_path (str): The directory where the file will be created.
            filename (str): The name of the file to create. Defaults to 'logical_network.json'.
            ring_size (int): The logical ring size.
    """
    config = {"logical-dims": [str(ring_size)]}
    file_path = os.path.join(folder_path, filename)
    with open(file_path, "w") as f:
        json.dump(config, f, indent=4)


def sweep():
    config_folder = "/app/examples/sweep-ns3/inputs"
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
            logical_filename = "logical_network.json"
            physical_filename = "physical_network.txt"
            gen_logical_config(
                folder_path=config_folder, filename=logical_filename, ring_size=size
            )
            gen_physical_config(
                folder_path=config_folder,
                filename=physical_filename,
                ring_size=size,
                n_links=N,
                m_jobs=M,
            )
            result = run_helper(coll_size=coll_size, logical_filename=logical_filename)
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
        "M conetnding jobs",
        "collective size",
        "cycles",
    ]
    filename = "sweep.csv"
    with open(filename, "w", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(header)
        csv_writer.writerows(sweep_results)


if __name__ == "__main__":
    sweep()
