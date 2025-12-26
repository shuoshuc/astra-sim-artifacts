import os
import argparse
import math
import json
import csv

from chakra.src.third_party.utils.protolib import encodeMessage as encode_message
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

BYTES_IN_MB = 1_048_576


def genSingleDummyTrace(args):
    trace_names = []
    # Extract the trace names from the provided list file.
    with open(args.dummy_trace_list, mode="r", encoding="utf-8") as f:
        trace_names = [row[0] for row in csv.reader(f)]

    # Create a dummy trace file for each trace name.
    for name in trace_names:
        with open(f"{args.output}/{name}", "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))
            node1 = ChakraNode()
            node1.id = 1
            node1.name = "DummyNode"
            node1.type = COMP_NODE
            node1.duration_micros = 1
            node1.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node1.attr.append(ChakraAttr(name="num_ops", int64_val=1))
            node1.attr.append(ChakraAttr(name="tensor_size", int64_val=1))
            encode_message(et, node1)


def gen1d(args):
    coll_size = args.coll_size_mb * BYTES_IN_MB
    comm_groups = {"0": []}

    for npu_id in range(math.prod(args.dims)):
        with open(f"{args.output}/trace.{npu_id}.et", "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))
            node1 = ChakraNode()
            node1.id = 1
            node1.name = "All-Reduce"
            node1.type = COMM_COLL_NODE
            node1.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node1.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
            node1.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size))
            # node1.attr.append(
            #     ChakraAttr(name="involved_dim", bool_list=BoolList(values=[True]))
            # )
            node1.attr.append(ChakraAttr(name="pg_name", string_val="0"))
            comm_groups["0"].append(npu_id)
            encode_message(et, node1)

    return comm_groups


def gen2d(args):
    coll_size = args.coll_size_mb * BYTES_IN_MB
    # X dimension from left to right, Y dimension from top to bottom.
    X, Y = args.dims
    comm_groups = {}

    for npu_id in range(math.prod(args.dims)):
        with open(f"{args.output}/trace.{npu_id}.et", "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))

            # ----- Dim 1 -----
            # all reduce along the X dimension
            node1 = ChakraNode()
            node1.id = 1
            node1.name = "All-Reduce-X"
            node1.type = COMM_COLL_NODE
            node1.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node1.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
            node1.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size))
            comm_group_x = str(npu_id // X)
            node1.attr.append(ChakraAttr(name="pg_name", string_val=comm_group_x))
            comm_groups.setdefault(comm_group_x, []).append(npu_id)
            encode_message(et, node1)

            # compute
            node2 = ChakraNode()
            node2.id = 2
            node2.name = "Compute"
            node2.type = COMP_NODE
            node2.duration_micros = 100
            node2.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node2.data_deps.append(node1.id)
            encode_message(et, node2)

            # ----- Dim 2 -----
            # all reduce along the Y dimension
            node3 = ChakraNode()
            node3.id = 3
            node3.name = "All-Reduce-Y"
            node3.type = COMM_COLL_NODE
            node3.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node3.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
            node3.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size))
            comm_group_y = str(npu_id % Y + Y)
            node3.attr.append(ChakraAttr(name="pg_name", string_val=comm_group_y))
            comm_groups.setdefault(comm_group_y, []).append(npu_id)
            node3.data_deps.append(node2.id)
            encode_message(et, node3)

    return comm_groups


def gen3d(args):
    coll_size = args.coll_size_mb * BYTES_IN_MB
    # X dimension from left to right,
    # Y dimension from top to bottom,
    # Z dimension from front to back.
    X, Y, Z = args.dims
    comm_groups = {}

    for npu_id in range(math.prod(args.dims)):
        # Convert NPU ID to 3D coordinates
        coord_x = npu_id % X
        coord_y = (npu_id // X) % Y
        coord_z = npu_id // (X * Y)
        with open(f"{args.output}/trace.{npu_id}.et", "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))

            # ----- Dim 1 -----
            # all reduce along the X dimension
            node1 = ChakraNode()
            node1.id = 1
            node1.name = "All-Reduce-X"
            node1.type = COMM_COLL_NODE
            node1.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node1.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
            node1.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size))
            comm_group_x = str(coord_y + coord_z * Y)
            node1.attr.append(ChakraAttr(name="pg_name", string_val=comm_group_x))
            comm_groups.setdefault(comm_group_x, []).append(npu_id)
            encode_message(et, node1)

            # compute
            node2 = ChakraNode()
            node2.id = 2
            node2.name = "Compute1"
            node2.type = COMP_NODE
            node2.duration_micros = 100
            node2.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node2.data_deps.append(node1.id)
            encode_message(et, node2)

            # ----- Dim 2 -----
            # all reduce along the Y dimension
            node3 = ChakraNode()
            node3.id = 3
            node3.name = "All-Reduce-Y"
            node3.type = COMM_COLL_NODE
            node3.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node3.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
            node3.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size))
            comm_group_y = str(coord_x + coord_z * X + Y * Z)
            node3.attr.append(ChakraAttr(name="pg_name", string_val=comm_group_y))
            comm_groups.setdefault(comm_group_y, []).append(npu_id)
            node3.data_deps.append(node2.id)
            encode_message(et, node3)

            # compute
            node4 = ChakraNode()
            node4.id = 4
            node4.name = "Compute2"
            node4.type = COMP_NODE
            node4.duration_micros = 100
            node4.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node4.data_deps.append(node3.id)
            encode_message(et, node4)

            # ----- Dim 3 -----
            # all reduce along the Z dimension
            node5 = ChakraNode()
            node5.id = 5
            node5.name = "All-Reduce-Z"
            node5.type = COMM_COLL_NODE
            node5.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node5.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
            node5.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size))
            comm_group_z = str(coord_x + coord_y * X + Y * Z + X * Z)
            node5.attr.append(ChakraAttr(name="pg_name", string_val=comm_group_z))
            comm_groups.setdefault(comm_group_z, []).append(npu_id)
            node5.data_deps.append(node4.id)
            encode_message(et, node5)

    return comm_groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manual Chakra trace generator.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--dims",
        type=lambda s: tuple(int(dim) for dim in s.split("x")),
        default=(4, 4, 4),
        help="Dimension size of an WxLxH Torus. Example: --dims 4x4x4",
    )
    parser.add_argument(
        "--coll_size_mb",
        type=int,
        default=1,
        help="The base collective size in MB (default: 1).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="trace",
        help="The name of the output directory (default: 'trace').",
    )
    parser.add_argument(
        "--comm_group_output",
        type=str,
        default="inputs",
        help="Path for the comm_groups JSON output.",
    )
    parser.add_argument(
        "--dummy_trace_list",
        type=str,
        default="",
        help="Path to a list containing the node names of dummy traces.",
    )

    args = parser.parse_args()
    trace_path = args.output
    if not os.path.exists(trace_path):
        os.makedirs(trace_path)

    # Fast path to only generate a dummy trace file and exit.
    if args.dummy_trace_list:
        genSingleDummyTrace(args)
        exit(0)

    comm_group_path = args.comm_group_output
    if not os.path.exists(comm_group_path):
        os.makedirs(comm_group_path)

    if len(args.dims) == 1:
        generate = gen1d
    elif len(args.dims) == 2:
        generate = gen2d
    elif len(args.dims) == 3:
        generate = gen3d
    else:
        raise ValueError("Only 1D, 2D, and 3D traces are supported.")

    comm_groups = generate(args)
    # Dump comm_groups to JSON file
    with open(os.path.join(comm_group_path, "comm_group.json"), "w") as f:
        comm_groups = {k: v for k, v in sorted(comm_groups.items())}
        json.dump(comm_groups, f, indent=2)
