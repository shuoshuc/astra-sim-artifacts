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


def translate_chakra_pb(orig_trace, out_trace):
    """
    Translates Chakra protobuf trace to the trace in the merged job.
    This function ensures the pg_name IDs are correctly mapped.
    Args:
        orig_trace (str): The original trace file path.
        out_trace (str): The output trace file path.
    """
    global_metadata = GlobalMetadata()
    node = ChakraNode()
    with open(orig_trace, "rb") as orig_et, open(out_trace, "wb") as out_et:
        decodeMessage(orig_et, global_metadata)
        encodeMessage(out_et, global_metadata)
        # TODO: implement proper pg_name translation.
        while decodeMessage(orig_et, node):
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
    for trace in traces:
        trace_path = os.path.join(input_path, trace)
        if not os.path.exists(trace_path):
            raise FileNotFoundError(f"Trace path does not exist: {trace_path}")

        for name in sorted(os.listdir(trace_path)):
            if not name.endswith(".et"):
                continue
            file_path = os.path.join(trace_path, name)
            xpu_id = placement_map[f"{trace}-{name.split('.')[-2]}"]
            translate_chakra_pb(
                orig_trace=file_path,
                out_trace=os.path.join(output_path, f"trace.{xpu_id}.et"),
            )


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
