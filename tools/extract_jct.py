import argparse
import json
import re
import pandas as pd


def parse_placement(placement_file):
    """
    Parses a JSON placement file into a reverse mapping from node to job name.
    Example config:
    {
        "J0-0": 0,
        "J0-1": 1,
        "J1-0": 2,
        "J1-1": 3,
    }
    "J0" is the job name, "J0-0" is the XPU 0 of job J0, which is mapped to physical
    XPU 0. Note that there could be more physical XPUs than required by the jobs.
    """
    node_to_job = {}
    with open(placement_file, "r") as f:
        for key, node_id in json.load(f).items():
            job_name = key.split("-", 1)[0]
            node_to_job[node_id] = job_name
    return node_to_job


def extrac_jct(log_path, placement_map, output_path):
    """
    Extracts JCT from the log file and writes to a CSV file.
    Args:
        log_path (str): Path to the log file containing per-XPU JCT.
        placement_map (Dict[int, str]): node ID to job name mapping.
        output_path (str): The path to the extracted JCT csv.
    """
    data = []
    pattern = re.compile(r"\[statistics\] \[trace\] (\d+), (\d+)")

    with open(log_path, "r") as f:
        for line in f:
            match = pattern.search(line)
            if not match:
                raise RuntimeError(f"No JCT found in line: {line}")

            node_id = int(match.group(1))
            jct = int(match.group(2))
            # TODO: Dummy nodes need special treatment.
            if node_id not in placement_map:
                raise RuntimeError(f"Node ID {node_id} not found in placement map.")

            data.append({"Job": placement_map[node_id], "JCT (nsec)": jct})

    df = pd.DataFrame(data)
    # Group by Job and take the max JCT
    result = df.groupby("Job")["JCT (nsec)"].max().reset_index()
    result.to_csv(output_path, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p",
        "--placement",
        help="Path to the placement config file.",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-l",
        "--log",
        help="Path to the log file containing per-XPU JCT.",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to the extracted JCT csv.",
        type=str,
        default="jct.csv",
    )
    args = parser.parse_args()

    # Parse the json config for job placement.
    placement_map = parse_placement(args.placement)
    # Extract and dump JCT.
    extrac_jct(args.log, placement_map, args.output)
