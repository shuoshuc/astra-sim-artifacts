import os
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


class MonotonicCounter:
    """
    Non-thread-safe monotonically increasing integer counter.
    Call fetch() to get the current value and increment it.
    """

    def __init__(self, start: int = 0):
        self._counter = start

    def fetch(self) -> int:
        v = self._counter
        self._counter += 1
        return v


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


def parse_comm_group(comm_group_file):
    """
    Parses a JSON communication group file into a dictionary.
    """
    with open(comm_group_file, "r") as f:
        return json.load(f)


def translate_chakra_pb(orig_trace, out_trace, trace_name, comm_group_map, placement_map):
    """
    Translates Chakra protobuf trace to the trace in the merged job.
    This function ensures the pg_name IDs are correctly mapped.
    Args:
        orig_trace (str): The original trace file path.
        out_trace (str): The output trace file path.
        trace_name (str): The trace name.
        comm_group_map (Dict[str, str]): Mapping from local comm group IDs to global comm group IDs.
        placement_map (Dict[str, int]): job and XPU IDs to physical XPU IDs mapping.
    """
    global_metadata = GlobalMetadata()
    node = ChakraNode()
    with open(orig_trace, "rb") as orig_et, open(out_trace, "wb") as out_et:
        decodeMessage(orig_et, global_metadata)
        encodeMessage(out_et, global_metadata)
        while decodeMessage(orig_et, node):
            if node.type == COMM_COLL_NODE:
                for attr in node.attr:
                    if attr.name != "pg_name":
                        continue
                    pg_name_str = attr.string_val
                    if pg_name_str not in comm_group_map:
                        raise ValueError(
                            f"pg_name {pg_name_str} not found in comm_group_map, trace: {orig_trace}"
                        )
                    attr.string_val = comm_group_map[pg_name_str]

            elif node.type == COMM_RECV_NODE:
                for attr in node.attr:
                    if attr.name != "comm_src":
                        continue
                    local_xpu_id = attr.int32_val
                    key = f"{trace_name}-{local_xpu_id}"
                    if key not in placement_map:
                        raise ValueError(
                            f"{attr.name} refers to {key}, but it's not found in placement_map, trace: {orig_trace}"
                        )
                    attr.int32_val = placement_map[key]
            elif node.type == COMM_SEND_NODE:
                for attr in node.attr:
                    if attr.name != "comm_dst":
                        continue
                    local_xpu_id = attr.int32_val
                    key = f"{trace_name}-{local_xpu_id}"
                    if key not in placement_map:
                        raise ValueError(
                            f"{attr.name} refers to {key}, but it's not found in placement_map, trace: {orig_trace}"
                        )
                    attr.int32_val = placement_map[key]
            encodeMessage(out_et, node)


def merge_traces(input_path, traces, output_path, placement_map):
    """
    Merges multiple Chakra traces into a single trace based on the provided placement map.
    Args:
        input_path (str): The folder containing the individual traces.
        traces (List[str]): List of trace names to merge.
        output_path (str): The folder to the merged trace.
        placement_map (Dict[str, int]): job and XPU IDs to physical XPU IDs mapping.
    """
    print(f"Merging traces from {input_path} into {output_path}")
    print(f"Traces to merge: {traces}")
    # A monotonically increasing index for global communication group IDs
    cg_index = MonotonicCounter(0)
    # Mapping job-local XPU IDs in communication groups (pg_name) -> global XPU IDs
    global_comm_group_map = {}
    for trace in traces:
        trace_path = os.path.join(input_path, trace)
        if not os.path.exists(trace_path):
            raise FileNotFoundError(f"Trace path does not exist: {trace_path}")

        # Parse trace-specific comm_group.json
        comm_group_path = os.path.join(trace_path, "comm_group.json")
        if not os.path.isfile(comm_group_path):
            raise FileNotFoundError(f"comm_group.json not found in {trace_path}")
        # Throwaway trace-specific communication group ID map for trace translation.
        trace_cg_map = {}
        for local_cg_id, xpu_list in parse_comm_group(comm_group_path).items():
            global_cg_id = str(cg_index.fetch())
            trace_cg_map[local_cg_id] = global_cg_id
            global_comm_group_map[global_cg_id] = [
                placement_map[f"{trace}-{int(local_xpu_id)}"] for local_xpu_id in xpu_list
            ]

        # Iterate over all .et files in the trace directory and translate them.
        for name in sorted(os.listdir(trace_path)):
            if not name.endswith(".et"):
                continue
            file_path = os.path.join(trace_path, name)
            xpu_id = placement_map[f"{trace}-{name.split('.')[-2]}"]
            translate_chakra_pb(
                orig_trace=file_path,
                out_trace=os.path.join(output_path, f"trace.{xpu_id}.et"),
                trace_name=name,
                comm_group_map=trace_cg_map,
                placement_map=placement_map,
            )

    # Dump the merged communication group config.
    merged_comm_group_path = os.path.join(output_path, "comm_group.json")
    with open(merged_comm_group_path, "w") as f:
        json.dump(global_comm_group_map, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge multiple Chakra traces.")
    parser.add_argument(
        "-i", "--input", help="Path to folder that contains all the traces."
    )
    parser.add_argument(
        "--traces",
        help="Comma-separated list of trace paths.",
        type=lambda s: [p.strip() for p in s.split(",") if p.strip()],
        default=None,
    )
    parser.add_argument("-o", "--output", help="Path to the merged trace.")
    parser.add_argument("-p", "--placement", help="Placement config file.")
    args = parser.parse_args()

    # Extract input/output paths and traces.
    input_path = args.input
    traces = sorted(args.traces)
    output_path = args.output

    # Parse the json config for job placement.
    placement_map = parse_placement(args.placement)

    merge_traces(input_path, traces, output_path, placement_map)