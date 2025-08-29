import os

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


def main() -> None:
    trace_path = "trace"
    # create directories
    if not os.path.exists(trace_path):
        os.makedirs(trace_path)

    # metadata
    npus_count = 256
    # 1MB
    coll_size = 1_048_576

    for npu_id in range(npus_count):
        output_filename = f"{trace_path}/trace.{npu_id}.et"
        with open(output_filename, "wb") as et:
            # Chakra Metadata
            encode_message(et, GlobalMetadata(version="0.0.4"))

            # Node 1 - compute
            node1 = ChakraNode()
            node1.id = 1
            node1.name = "Compute-50us"
            node1.type = COMP_NODE
            node1.duration_micros = 50
            node1.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            encode_message(et, node1)

            # Node 2 - all gather
            node2 = ChakraNode()
            node2.id = 2
            node2.name = "All-Gather"
            node2.type = COMM_COLL_NODE
            node2.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node2.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_GATHER))
            node2.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size * 2))
            node2.attr.append(
                ChakraAttr(name="involved_dim", bool_list=BoolList(values=[True, False]))
            )
            node2.data_deps.append(node1.id)
            encode_message(et, node2)

            # Node 3 - all reduce
            node3 = ChakraNode()
            node3.id = 1
            node3.name = "All-Reduce"
            node3.type = COMM_COLL_NODE
            node3.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node3.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_REDUCE))
            node3.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size))
            node3.attr.append(
                ChakraAttr(name="involved_dim", bool_list=BoolList(values=[False, True]))
            )
            node3.data_deps.append(node2.id)
            encode_message(et, node3)


if __name__ == "__main__":
    main()
