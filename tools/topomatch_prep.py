import argparse
import os
import json
import bisect
import numpy as np
from collections import defaultdict

from chakra.src.third_party.utils.protolib import decodeMessage
from chakra.schema.protobuf.et_def_pb2 import (
    Node as ChakraNode,
    COMM_COLL_NODE,
    COMM_SEND_NODE,
    GlobalMetadata,
)


def find_next_wrap(sorted_list, n):
    # Find the position where n could be inserted after existing entries
    idx = bisect.bisect_right(sorted_list, n)
    # If the index is equal to the length of the list,
    # n is the largest element (or greater than all elements), so wrap around.
    if idx == len(sorted_list):
        return sorted_list[0]
    return sorted_list[idx]


def process_trace(trace_path):
    # Aggregators
    coll_volumes = defaultdict(int)  # pg_name -> total_bytes
    send_volumes = defaultdict(int)  # comm_dst -> total_bytes

    with open(trace_path, "rb") as f:
        # Skip metadata
        gm = GlobalMetadata()
        decodeMessage(f, gm)
        node = ChakraNode()
        while decodeMessage(f, node):
            if node.type == COMM_COLL_NODE:
                pg_name = None
                comm_size = 0
                for attr in node.attr:
                    if attr.name == "pg_name":
                        pg_name = attr.string_val
                    elif attr.name == "comm_size":
                        comm_size = attr.int64_val
                if pg_name is not None:
                    coll_volumes[pg_name] += comm_size

            elif node.type == COMM_SEND_NODE:
                comm_dst = None
                comm_size = 0
                for attr in node.attr:
                    if attr.name == "comm_dst":
                        comm_dst = attr.int32_val
                    elif attr.name == "comm_size":
                        comm_size = attr.int64_val
                if comm_dst is not None:
                    send_volumes[comm_dst] += comm_size

    return coll_volumes, send_volumes


def build_traffic_matrix(entries, num_nodes):
    matrix = np.zeros((num_nodes, num_nodes), dtype=int)
    # src and dst are integers, vol is in MB.
    for src, dst, vol in entries:
        matrix[src, dst] += vol
    return matrix


def main():
    parser = argparse.ArgumentParser(
        description="Sum communication volumes from Chakra traces in a folder."
    )
    parser.add_argument(
        "-f", "--trace_folder", required=True, help="Directory containing .et files"
    )
    parser.add_argument(
        "-m", "--matrix_output", required=True, help="Output file for the traffic matrix"
    )
    args = parser.parse_args()

    # Construct files as a list of tuples (N, filename)
    files = []
    comm_group = {}
    for f in os.listdir(args.trace_folder):
        if f.endswith(".et"):
            try:
                n = int(f.split(".")[-2])
            except (IndexError, ValueError):
                n = -1
            files.append((n, f))
        if f.endswith(".json"):
            with open(os.path.join(args.trace_folder, f), "r") as json_file:
                comm_group = json.load(json_file)
    files.sort()

    traffic_entries = []
    for n, filename in files:
        coll_volumes, send_volumes = process_trace(
            os.path.join(args.trace_folder, filename)
        )

        # print(f"Node {n}")
        if coll_volumes:
            for pg_name, volume in sorted(coll_volumes.items()):
                next_node = find_next_wrap(sorted(comm_group[pg_name]), n)
                # print(
                #     f"To {next_node} (PG {pg_name} [{comm_group[pg_name]}]): {volume / 1000000} MB"
                # )
                traffic_entries.append((int(n), int(next_node), int(volume / 1000000)))

        if send_volumes:
            for dst, volume in sorted(send_volumes.items()):
                # print(f"To dst {dst}: {volume / 1000000} MB")
                traffic_entries.append((int(n), int(dst), int(volume / 1000000)))

    matrix = build_traffic_matrix(traffic_entries, len(files))
    np.savetxt(args.matrix_output, matrix, fmt="%d", delimiter=" ")


if __name__ == "__main__":
    main()
