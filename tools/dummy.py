import os
import argparse

from chakra.src.third_party.utils.protolib import encodeMessage, decodeMessage
from chakra.schema.protobuf.et_def_pb2 import (
    Node as ChakraNode,
    GlobalMetadata,
    AttributeProto as ChakraAttr,
    COMP_NODE,
)


def insert_dummy_node(orig_trace, out_trace, duration_micros):
    """
    Prepend a dummy compute node to beginning of trace to delay execution for
    that node.
    Args:
        orig_trace (str): Path to the original .et trace file.
        out_trace (str): Path to write the modified .et trace file.
        duration_micros (int): Duration of the dummy node in microseconds.
    """
    global_metadata = GlobalMetadata()
    nodes = []

    # Read trace
    with open(orig_trace, "rb") as f:
        decodeMessage(f, global_metadata)
        node = ChakraNode()
        while decodeMessage(f, node):
            copied = ChakraNode()
            copied.CopyFrom(node)
            nodes.append(copied)
            node.Clear()

    # Create dummy node
    dummy_node = ChakraNode()
    dummy_node.id = 2  # id of first node in trace is 2
    dummy_node.name = "DummyNode"
    dummy_node.type = COMP_NODE
    dummy_node.duration_micros = duration_micros
    dummy_node.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
    dummy_node.attr.append(ChakraAttr(name="num_ops", int64_val=1))
    dummy_node.attr.append(ChakraAttr(name="tensor_size", int64_val=1))
    dummy_node.attr.append(ChakraAttr(name="op_type", string_val="E"))

    # Reindex other nodes
    for n in nodes:
        n.id += 1
        for i, dep in enumerate(n.data_deps):
            n.data_deps[i] = dep + 1

    # Make first compute node depend on dummy node
    first_comp = next((n for n in nodes if n.type == COMP_NODE), None)
    if first_comp:
        first_comp.data_deps.append(dummy_node.id)

    # Write modified trace with dummy node as first node
    with open(out_trace, "wb") as out_f:
        encodeMessage(out_f, global_metadata)
        encodeMessage(out_f, dummy_node)
        for n in nodes:
            encodeMessage(out_f, n)


def insert_dummy_node_to_dir(input_dir, output_dir, duration_micros):
    """
    Adds a dummy node to every .et file in a directory.
    Args:
        input_dir (str): Path to folder containing original .et trace files.
        output_dir (str): Path to folder to write modified .et files.
        duration_micros (int): Duration of the dummy node in microseconds.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    et_files = sorted([f for f in os.listdir(input_dir) if f.endswith(".et")])
    if not et_files:
        raise FileNotFoundError(f"No .et files found in {input_dir}")

    print(f"Writing traces from '{input_dir}' to '{output_dir}'")

    for et_file in et_files:
        input_path = os.path.join(input_dir, et_file)
        output_path = os.path.join(output_dir, et_file)
        insert_dummy_node(input_path, output_path, duration_micros)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepend a dummy (delay) node to start of all .et traces."
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        help="Path to folder containing original .et trace files.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Path to folder to write modified .et files.",
    )
    parser.add_argument(
        "--duration_micros",
        type=int,
        default=5_000_000,  # 5 seconds in microseconds
        help="Duration of the dummy node in microseconds (default: 5 seconds = 5,000,000 µs).",
    )

    args = parser.parse_args()

    insert_dummy_node_to_dir(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        duration_micros=args.duration_micros,
    )
