#!/usr/bin/env python3
import os
import json
import shutil
import subprocess
import atexit
import re 
import argparse
import sys

# ==== CONFIG ====
WORKLOAD1_DIR = "/app/examples/multitenancy/inputs/denseA"
WORKLOAD2_DIR = "/app/examples/multitenancy/inputs/denseB"
OUTPUT_NAME = "mergedAB"
OUTPUT_DIR = "/app/examples/multitenancy/inputs/" + OUTPUT_NAME
COMM_GROUP1 = "/app/examples/multitenancy/inputs/denseA/denseA.json"
COMM_GROUP2 = "/app/examples/multitenancy/inputs/denseB/denseB.json"
# =================

CHAKRA_ROOT = "/app/chakra"  
TEMP1_DIR = "workload1_json_tmp"
TEMP2_DIR = "workload2_json_tmp"
MERGED_TEMP_DIR = "merged_json_tmp"

# ====== reverse chakra jsonizer
if CHAKRA_ROOT not in sys.path:
    sys.path.insert(0, CHAKRA_ROOT)
from google.protobuf.json_format import Parse
from schema.protobuf.et_def_pb2 import GlobalMetadata
from schema.protobuf.et_def_pb2 import Node as ChakraNode
from src.third_party.utils.protolib import encodeMessage as encode_message

def reverse_json_to_et(input_filename, output_filename):
    """
    Convert concatenated JSON back to Chakra ET binary.
    """
    import gzip  # make sure to import gzip here, used in open_file_wr

    def open_file_wr(out_file):
        """Open file for writing (gzip if .gz, else normal binary)."""
        try:
            if out_file.endswith(".gz"):
                return gzip.open(out_file, "wb")
            else:
                return open(out_file, "wb")
        except IOError:
            print("Failed to open ", out_file, " for writing")
            exit(-1)

    # Read JSON
    with open(input_filename, "r") as file:
        json_str = file.read()

    # Split concatenated JSON
    json_objects = []
    brace_level = 0
    current = ""
    for ch in json_str:
        current += ch
        if ch == "{":
            brace_level += 1
        elif ch == "}":
            brace_level -= 1
            if brace_level == 0:
                json_objects.append(current.strip())
                current = ""

    if not json_objects:
        raise ValueError(f"No valid JSON objects in {input_filename}")

    # Open output ET file
    output_file = open_file_wr(output_filename)

    # First object is GlobalMetadata
    global_metadata = GlobalMetadata()
    Parse(json_objects[0], global_metadata)
    encode_message(output_file, global_metadata)

    # Remaining are Node messages
    for obj_str in json_objects[1:]:
        node = ChakraNode()
        Parse(obj_str, node)
        encode_message(output_file, node)

    output_file.close()
    # print(f"✅ Wrote {len(json_objects)-1} nodes and metadata to {output_filename}")

# ====== end reverse chakra jsonizer

def safe_rmtree(path):
    """Remove a directory if it exists."""
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def natural_key(s):
    """Sort filenames in human order, e.g. file.2 before file.10"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def run_jsonizer(input_file, output_file):
    """Run chakra_jsonizer command inside /app/chakra."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    abs_input = os.path.abspath(input_file)
    abs_output = os.path.abspath(output_file)
    cmd = [
        "chakra_jsonizer",
        "--input_filename", abs_input,
        "--output_filename", abs_output,
    ]
    try:
        subprocess.run(cmd, cwd=CHAKRA_ROOT, check=True)
        # print(f"✅ JSONized: {input_file} → {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to JSONize {input_file}: {e}")


def jsonize_folder(et_dir, out_dir):
    """JSONize every .et file in a folder using chakra_jsonizer."""
    safe_rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    for root, _, files in os.walk(et_dir):
        for f in sorted(files, key=natural_key):  # <-- natural sort
            if f.endswith(".et"):
                src = os.path.join(root, f)
                rel_path = os.path.relpath(src, et_dir)
                dst = os.path.join(out_dir, rel_path.replace(".et", ".json"))
                run_jsonizer(src, dst)
    return out_dir


def load_multi_json(path):
    """Load a file containing multiple concatenated JSON objects."""
    with open(path, "r") as f:
        content = f.read().strip()

    objs = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(content):
        content_slice = content[idx:].lstrip()
        if not content_slice:
            break
        obj, end = decoder.raw_decode(content_slice)
        objs.append(obj)
        idx += len(content[idx:]) - len(content_slice) + end
    return objs


def save_multi_json(objs, path):
    """Save a list of JSON objects as concatenated JSON objects in a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for obj in objs:
            json.dump(obj, f, indent=2)


def offset_pg_name_only_file(in_path, out_path, group_offset, node_offset):
    """Read concatenated JSON objects, offset pg_name and comm_src/dst, and write back."""
    objs = load_multi_json(in_path)
    for node in objs:
        if "attr" in node and isinstance(node["attr"], list):
            for a in node["attr"]:
                name = a.get("name")

                # Offset pg_name by group_offset
                if name == "pg_name":
                    try:
                        if "int64Val" in a:
                            a["int64Val"] = str(int(a["int64Val"]) + group_offset)
                        elif "stringVal" in a:
                            a["stringVal"] = str(int(a["stringVal"]) + group_offset)
                    except Exception:
                        a["stringVal"] = f"{a.get('stringVal', '')}_shifted"

                # Offset comm_src and comm_dst by node_offset
                elif name in ("comm_src", "comm_dst"):
                    try:
                        if "int32Val" in a:
                            a["int32Val"] = int(a["int32Val"]) + node_offset
                        elif "int64Val" in a:
                            a["int64Val"] = str(int(a["int64Val"]) + node_offset)
                    except Exception:
                        pass

    save_multi_json(objs, out_path)


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


import os, json

def load_json(path):
    with open(path) as f:
        return json.load(f)

def merge_comm_groups(path1, path2, out_path, overlap_mode="disjoint"):
    """
    Merge communicator group JSONs from two workloads.

    overlap_mode:
      - "disjoint": workloads occupy separate physical nodes (default)
      - "interleaved": workloads share nodes in an interleaved mapping,
                       but keep communicator groups distinct
      - "shared": (optional future mode) workloads share group IDs
    """
    group1 = load_json(path1)
    group2 = load_json(path2)

    # ---- compute offsets ----
    numeric_group_keys = []
    for k in group1.keys():
        try:
            numeric_group_keys.append(int(k))
        except Exception:
            pass
    group_offset = (max(numeric_group_keys)) if numeric_group_keys else len(group1)

    # compute node_offset as 1 + max node id in group1
    max_node = -1
    for v in group1.values():
        if isinstance(v, list):
            for item in v:
                try:
                    max_node = max(max_node, int(item))
                except Exception:
                    pass
    node_offset = max_node + 1 if max_node >= 0 else 0

    merged = {}

    # ---- Workload 1: copy as-is ----
    for name, ranks in group1.items():
        merged[str(name)] = [int(r) for r in ranks]

    # ---- Workload 2: offset differently depending on overlap mode ----
    if overlap_mode == "disjoint":
        # normal behavior: simply offset by node_offset
        for name, ranks in group2.items():
            try:
                new_name = str(int(name) + group_offset)
            except Exception:
                new_name = f"{name}_w2"

            new_ranks = [int(r) + node_offset for r in ranks]
            merged[new_name] = new_ranks

    elif overlap_mode == "interleaved":
        # interleaving: map workload2 ranks to odd indices
        # workload1 → even nodes, workload2 → odd nodes
        for name, ranks in group2.items():
            try:
                new_name = str(int(name) + group_offset)
            except Exception:
                new_name = f"{name}_w2"

            new_ranks = []
            for r in ranks:
                r_int = int(r)
                interleaved_rank = 2 * r_int + 1  # odd-numbered nodes
                new_ranks.append(interleaved_rank)
            merged[new_name] = new_ranks

        # also remap workload1 ranks to even-numbered nodes for consistency
        for name in list(group1.keys()):
            merged[name] = [2 * int(r) for r in group1[name]]

    else:
        raise ValueError(f"Invalid overlap_mode: {overlap_mode}")

    # ---- save result ----
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(merged, f, separators=(",", ":"))

    print(f"Merged communicator groups saved to: {out_path}")
    print(f"    group_offset = {group_offset}, node_offset = {node_offset}, mode = {overlap_mode}")
    return group_offset, node_offset




def merge_workloads():
    # Ensure cleanup happens on exit, even if interrupted
    atexit.register(lambda: [safe_rmtree(d) for d in [TEMP1_DIR, TEMP2_DIR, MERGED_TEMP_DIR]])

    # Step 0: JSONize both workloads
    print("JSONizing workload 1...")
    json1 = jsonize_folder(WORKLOAD1_DIR, TEMP1_DIR)
    print("JSONizing workload 2...")
    json2 = jsonize_folder(WORKLOAD2_DIR, TEMP2_DIR)

    # Step 1: Prepare output dirs
    abs_output_dir = os.path.abspath(OUTPUT_DIR)
    abs_merged_tmp_dir = os.path.abspath(MERGED_TEMP_DIR)
    safe_rmtree(abs_output_dir)
    safe_rmtree(abs_merged_tmp_dir)
    os.makedirs(abs_output_dir, exist_ok=True)
    os.makedirs(abs_merged_tmp_dir, exist_ok=True)

    # Step 2: Merge communicator groups
    merged_comm_path = os.path.join(abs_output_dir, OUTPUT_NAME + ".json")
    group_offset, node_offset = merge_comm_groups(COMM_GROUP1, COMM_GROUP2, merged_comm_path, "disjoint")

    # Step 3 & 4: Copy JSON files into temporary merged dir
    file_counter = 0

    # Workload1 (no change)
    for root, _, files in os.walk(json1):
        for f in sorted(files, key=natural_key):  # <-- natural sort
            if f.endswith(".json"):
                src = os.path.join(root, f)
                dst = os.path.join(abs_merged_tmp_dir, f"{OUTPUT_NAME}.{file_counter}.json")
                file_counter += 1
                shutil.copy(src, dst)

    # Workload2 (offset pg_name)
    for root, _, files in os.walk(json2):
        for f in sorted(files, key=natural_key):  # <-- natural sort
            if f.endswith(".json"):
                src = os.path.join(root, f)
                dst = os.path.join(abs_merged_tmp_dir, f"{OUTPUT_NAME}.{file_counter}.json")
                file_counter += 1
                offset_pg_name_only_file(src, dst, group_offset, node_offset)

    # Step 5: Reverse each merged JSON using Chakra reverse.py
    print("Converting merged JSON files to Chakra .et files...")
    for f in sorted(os.listdir(abs_merged_tmp_dir), key=natural_key):  # <-- natural sort
        if f.endswith(".json"):
            input_path = os.path.join(abs_merged_tmp_dir, f)
            output_filename = os.path.splitext(f)[0] + ".et"
            output_path = os.path.join(abs_output_dir, output_filename)

            reverse_json_to_et(os.path.abspath(input_path), os.path.abspath(output_path))

            # print(f"✅ Reversed {f} → {output_filename}")

    print(f"Final reversed .et files saved to: {abs_output_dir}")

    # Final cleanup
    for d in [TEMP1_DIR, TEMP2_DIR, MERGED_TEMP_DIR]:
        safe_rmtree(d)


if __name__ == "__main__":
    merge_workloads()
