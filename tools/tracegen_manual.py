import os
import argparse
import math
import json
import csv
from pathlib import Path
from create_jobspec import parse_jobspec

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


def genSingleDummyTrace(output, name):
    job_path = output / name
    job_path.mkdir(parents=True, exist_ok=True)
    with open(job_path / f"{name}.0.et", "wb") as et:
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
    with open(job_path / f"{name}.json", "w") as f:
        json.dump({}, f, indent=2)


def gen1d(output, name, shape, coll_size):
    """
    Generate 1D collective trace, assuming all nodes belong to the same ring.
    """
    comm_groups = {"0": []}
    job_path = output / name
    job_path.mkdir(parents=True, exist_ok=True)

    for npu_id in range(math.prod(shape)):
        with open(job_path / f"{name}.{npu_id}.et", "wb") as et:
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
    with open(job_path / f"{name}.json", "w") as f:
        comm_groups = {k: v for k, v in sorted(comm_groups.items())}
        json.dump(comm_groups, f, indent=2)


def gen2d(output, name, shape, coll_size):
    # X dimension from left to right, Y dimension from top to bottom.
    X, Y = shape
    comm_groups = {}
    job_path = output / name
    job_path.mkdir(parents=True, exist_ok=True)

    for npu_id in range(math.prod(shape)):
        with open(job_path / f"{name}.{npu_id}.et", "wb") as et:
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

    with open(job_path / f"{name}.json", "w") as f:
        comm_groups = {k: v for k, v in sorted(comm_groups.items())}
        json.dump(comm_groups, f, indent=2)


def gen3d(output, name, shape, coll_size):
    # X dimension from left to right,
    # Y dimension from top to bottom,
    # Z dimension from front to back.
    X, Y, Z = shape
    comm_groups = {}
    job_path = output / name
    job_path.mkdir(parents=True, exist_ok=True)

    for npu_id in range(math.prod(shape)):
        # Convert NPU ID to 3D coordinates
        coord_x = npu_id % X
        coord_y = (npu_id // X) % Y
        coord_z = npu_id // (X * Y)
        with open(job_path / f"{name}.{npu_id}.et", "wb") as et:
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

    with open(job_path / f"{name}.json", "w") as f:
        comm_groups = {k: v for k, v in sorted(comm_groups.items())}
        json.dump(comm_groups, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manual Chakra trace generator.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--coll_size_mb",
        type=int,
        default=1,
        help="The base collective size in MB (default: 1).",
    )
    parser.add_argument(
        "-J",
        "--jobspec",
        type=str,
        default="",
        help="Path to the job spec containing a list of jobs.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="trace",
        help="The top-level output directory (default: 'trace').",
    )

    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    jobs = parse_jobspec(args.jobspec)
    for name, [shape, label] in jobs.items():
        # Main jobs should be generated by STG.
        if label == 'M':
            continue

        if math.prod(shape) == 1:
            genSingleDummyTrace(output, name)
            continue

        coll_size = args.coll_size_mb * BYTES_IN_MB
        new_shape = []
        for dim in shape:
            if dim > 1:
                new_shape.append(dim)
        if len(new_shape) == 1:
            gen1d(output, name, shape, coll_size)
        elif len(new_shape) == 2:
            gen2d(output, name, tuple(new_shape), coll_size)
        elif len(new_shape) == 3:
            gen3d(output, name, shape, coll_size)
