import os
import sys
import argparse
import json

from chakra.src.third_party.utils.protolib import encodeMessage, decodeMessage
from chakra.schema.protobuf.et_def_pb2 import (
    Node as ChakraNode,
    BoolList,
    GlobalMetadata,
    AttributeProto as ChakraAttr,
    COMP_NODE,
    COMM_COLL_NODE,
    ALL_REDUCE,
    ALL_GATHER,
)


def parse_placement(placement_file):
    """
    Parses a JSON placement file into a dictionary.
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
    with open(placement_file, "r") as f:
        return json.load(f)

def build_job_xpu_map(jobs, placement_map):
    """
    Builds a dictionary mapping each job to its own map of old XPU IDs
    to new XPU IDs.

    Args:
        jobs (List[str]): List of job names (e.g., ["J0", "J1"]).
        placement_map (Dict[str, int]): Mapping like {"J0-0": 0, "J0-1": 1, "J1-0": 2, ...}

    Returns:
        Dict[str, Dict[int, int]]: Mapping from job name → map of{old_xpu_id: new_xpu_id}
    """
    job_xpu_map = {}
    for job in jobs:
        xpu_map = {}
        for key, global_xpu in placement_map.items():
            if key.startswith(f"{job}-"):
                local_xpu = int(key.split("-")[1])
                xpu_map[local_xpu] = global_xpu
        job_xpu_map[job] = xpu_map
    return job_xpu_map


def merge_comm_groups(input_path, jobs, output_path, placement_map):
    """
    Merges each workload's comm group file into 1 based on placement_map
    Args:
        input_path (str): The folder containing the individual jobs.
        jobs (List[str]): List of job names to merge.
        output_path (str): The folder to the merged job.
        placement_map (Dict[str, int]): job and XPU IDs to physical XPU IDs mapping.
    Returns:
        Dict[str, int]: Mapping of job name to comm_group offset used for pg_name remapping
    """
    merged_groups = {}
    offset = 0
    offset_map = {}

    for job in jobs:
        comm_file = os.path.join(input_path, job, f"{job}.json")
        if not os.path.exists(comm_file):
            print(f"Warning: {comm_file} not found, skipping.")
            continue

        with open(comm_file, "r") as f:
            groups = json.load(f)
        
        offset_map[job] = offset

        for gid_str, members in groups.items():
            gid = int(gid_str)
            new_gid = gid + offset
            new_members = [placement_map[f"{job}-{m}"] for m in members]
            merged_groups[str(new_gid)] = new_members

        offset += len(groups)

    out_path = os.path.join(output_path, "comm_group.json")
    with open(out_path, "w") as f:
        json.dump(merged_groups, f, indent=4)
    print(f"Merged comm groups written to {out_path}")

    return offset_map


def translate_chakra_pb(orig_trace, out_trace, comm_group_offset, xpu_map):
    """
    Translates Chakra protobuf trace to the trace in the merged job.
    This function ensures the pg_name IDs are correctly mapped.
    Args:
        orig_trace (str): The original trace file path.
        out_trace (str): The output trace file path.
        comm_group_offset (int): The comm_group offset for this trace's job
        xpu_map (Dict[int, int]): original XPU id to new XPU id mapping for this trace's job
    """
    global_metadata = GlobalMetadata()
    node = ChakraNode()
    with open(orig_trace, "rb") as orig_et, open(out_trace, "wb") as out_et:
        decodeMessage(orig_et, global_metadata)
        encodeMessage(out_et, global_metadata)
        while decodeMessage(orig_et, node):
            for attr in node.attr:
                # Update pg_name <= pg_name + comm_group_offset
                if attr.name == "pg_name":
                    try:
                        original_pg = int(attr.string_val)
                        attr.string_val = str(original_pg + comm_group_offset)
                        # print(f"{orig_trace}: {attr.name} string = {original_pg} -> {attr.string_val}")
                    except ValueError:
                        print(f"Warning: pg_name field not integer-like in {src}: '{attr.string_val}'")
                
                # Update comm_src/comm_dst <= new node from placement_map
                if attr.name in ("comm_src", "comm_dst"):
                    if hasattr(attr, "int32Val") and attr.int32Val is not None:
                        original_id = attr.int32Val
                        attr.int32Val = xpu_map[original_id]
                        # print(f"{orig_trace}: {attr.name} (int32Val) = {original_id} -> {attr.int32Val}")
                    elif hasattr(attr, "int64Val") and attr.int64Val is not None:
                        original_id = attr.int64Val
                        attr.int64Val = xpu_map[original_id]
                        # print(f"{orig_trace}: {attr.name} (int64Val) = {original_id} -> {attr.int64Val}")
                    else:
                        print(f"Warning: {attr.name} has no int32Val/int64Val in {src}")

            encodeMessage(out_et, node)


def merge_jobs(input_path, jobs, output_path, placement_map, offset_map):
    """
    Merges multiple Chakra jobs into a single job based on the provided placement map.
    Args:
        input_path (str): The folder containing the individual jobs.
        jobs (List[str]): List of job names to merge.
        output_path (str): The folder to the merged job.
        placement_map (Dict[str, int]): job and XPU IDs to physical XPU IDs mapping.
        offset_map (Dict[str, int]): job name to number of comm_groups mapping
    """
    print(f"Merging jobs from {input_path} into {output_path}")
    print(f"Jobs to merge: {jobs}")

    jobs_xpu_map = build_job_xpu_map(jobs, placement_map)
    for job in jobs:
        job_path = os.path.join(input_path, job)
        if not os.path.exists(job_path):
            raise FileNotFoundError(f"job path does not exist: {job_path}")

        for name in sorted(os.listdir(job_path)):
            if not name.endswith(".et"):
                continue
            trace_path = os.path.join(job_path, name)
            xpu_id = placement_map[f"{job}-{name.split('.')[-2]}"]
            translate_chakra_pb(
                orig_trace=trace_path,
                out_trace=os.path.join(output_path, f"trace.{xpu_id}.et"),
                comm_group_offset=offset_map[job],
                xpu_map=jobs_xpu_map[job]
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge multiple Chakra jobs.")
    parser.add_argument(
        "-i", "--input", help="Path to folder that contains all the jobs."
    )
    parser.add_argument(
        "--jobs",
        help="Comma-separated list of job names.",
        type=lambda s: [p.strip() for p in s.split(",") if p.strip()],
        default=None,
    )
    parser.add_argument("-o", "--output", help="Path to the merged job.")
    parser.add_argument("-p", "--placement", help="Placement config file.")
    args = parser.parse_args()

    # Extract input/output paths and jobs.
    input_path = args.input
    jobs = sorted(args.jobs)
    output_path = args.output

    # Parse the json config for job placement.
    placement_map = parse_placement(args.placement)

    offset_map = merge_comm_groups(input_path, jobs, output_path, placement_map)
    merge_jobs(input_path, jobs, output_path, placement_map, offset_map)
    