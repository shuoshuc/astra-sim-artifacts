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


def gen_trace(output, name, shape, coll_sizes):
    """
    Generate a Chakra trace for one job whose total NPU count is > 1.

    shape:       3-tuple (DP, TP, PP).
    coll_sizes:  3-list of bytes [DP_size, TP_size, PP_size].

    Emits one All-Reduce per dim with shape[i] > 1, in DP -> TP -> PP order.
    Collectives are chained sequentially via data_deps with a Compute node
    (duration_micros=100, is_cpu_op=False) between each consecutive pair.
    Node `.name` for the i-th dim collective is "All-Reduce-X" (i=0),
    "All-Reduce-Y" (i=1), or "All-Reduce-Z" (i=2).
    """
    DP, TP, PP = shape
    dim_names = ["X", "Y", "Z"]

    # Indices of dims that participate in a collective, in 0..2 order.
    active = [i for i, d in enumerate(shape) if d > 1]

    comm_groups = {}
    job_path = output / name
    job_path.mkdir(parents=True, exist_ok=True)

    for npu_id in range(math.prod(shape)):
        xc = npu_id % DP
        yc = (npu_id // DP) % TP
        zc = npu_id // (DP * TP)

        # Per-dim comm-group IDs. Offsets keep IDs disjoint across dims so
        # the merged comm_groups dict has unique keys.
        group_ids = [
            yc + zc * TP,                         # dim 0 (DP / X)
            xc + zc * DP + (TP * PP),             # dim 1 (TP / Y)
            xc + yc * DP + (TP * PP) + (DP * PP), # dim 2 (PP / Z)
        ]

        with open(job_path / f"{name}.{npu_id}.et", "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))

            prev_id = None
            next_id = 1
            for k, dim in enumerate(active):
                if prev_id is not None:
                    comp = ChakraNode()
                    comp.id = next_id
                    next_id += 1
                    comp.name = f"Compute{k}"
                    comp.type = COMP_NODE
                    comp.duration_micros = 100
                    comp.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
                    # Required by the simulator's roofline path
                    # (Workload::issue_comp). Without these the COMP_NODE
                    # is dropped and the chained collective never runs.
                    comp.attr.append(ChakraAttr(name="num_ops", int64_val=1))
                    comp.attr.append(ChakraAttr(name="tensor_size", int64_val=1))
                    comp.data_deps.append(prev_id)
                    encode_message(et, comp)
                    prev_id = comp.id

                coll = ChakraNode()
                coll.id = next_id
                next_id += 1
                coll.name = f"All-Reduce-{dim_names[dim]}"
                coll.type = COMM_COLL_NODE
                coll.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
                coll.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
                coll.attr.append(ChakraAttr(name="comm_size", int64_val=coll_sizes[dim]))
                gid = str(group_ids[dim])
                coll.attr.append(ChakraAttr(name="pg_name", string_val=gid))
                comm_groups.setdefault(gid, []).append(npu_id)
                if prev_id is not None:
                    coll.data_deps.append(prev_id)
                encode_message(et, coll)
                prev_id = coll.id

    with open(job_path / f"{name}.json", "w") as f:
        comm_groups = {k: v for k, v in sorted(comm_groups.items())}
        json.dump(comm_groups, f, indent=2)


def _parse_coll_sizes_mb(s):
    parts = str(s).split(',')
    if len(parts) == 1:
        return [int(parts[0])] * 3
    if len(parts) == 3:
        return [int(p) for p in parts]
    raise argparse.ArgumentTypeError(
        "expected 1 or 3 comma-separated ints (got %r)" % s
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manual Chakra trace generator.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--coll_size_mb",
        type=_parse_coll_sizes_mb,
        default=[1, 1, 1],
        help="Base collective size in MB. Either a single int (broadcast to "
             "all DP/TP/PP dims) or a comma-separated DP,TP,PP triple. "
             "Default: 1 (broadcast).",
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

    coll_sizes = [s * BYTES_IN_MB for s in args.coll_size_mb]

    jobs = parse_jobspec(args.jobspec)
    for name, [shape, label] in jobs.items():
        # Main jobs should be generated by STG.
        if label == 'M':
            continue

        if math.prod(shape) == 1:
            genSingleDummyTrace(output, name)
            continue

        gen_trace(output, name, shape, coll_sizes)
