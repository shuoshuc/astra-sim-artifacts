import argparse
import itertools
import json
import random
from natsort import natsorted
from math import prod
from placement_lib import FirstFit


def init_torus_blocks(dims, B):
    """
    Initialize a list of lists, where each list contains node indices of a BxBxB block in a WxLxH torus.
    Nodes in the torus are indexed in plane-major order.
    """
    for dim in dims:
        if dim % B != 0:
            raise ValueError("Block size must divide each torus dimension exactly.")

    blocks = []
    W, L, H = dims
    for z_start, y_start, x_start in itertools.product(
        range(0, H, B), range(0, L, B), range(0, W, B)
    ):
        block = []
        for z, y, x in itertools.product(
            range(z_start, z_start + B),
            range(y_start, y_start + B),
            range(x_start, x_start + B),
        ):
            block.append(z * (L * W) + y * W + x)
        blocks.append(block)
    return blocks


def init_job_blocks(jobs, B):
    """
    For each job, breaks it into BxBxB blocks and returns a dictionary mapping job names to list of lists of node indices.
    The job shape is denoted by (D, T, P) where D is DP degree, T is TP degree, and P is PP degree.
    Node index in a job also follow plane-major ordering.
    """
    job_blocks = {}
    for name, dims in jobs.items():
        D, T, P = dims
        job_block_indices = []

        for p_start, t_start, d_start in itertools.product(
            range(0, P, B), range(0, T, B), range(0, D, B)
        ):
            block = []
            for p, t, d in itertools.product(
                range(p_start, p_start + B),
                range(t_start, t_start + B),
                range(d_start, d_start + B),
            ):
                block.append(p * (T * D) + t * D + d)
            job_block_indices.append(block)
        job_blocks[name] = job_block_indices

    return job_blocks


def parse_jobspec(file_path):
    """
    Parses a jobspec file (CSV: Name,D,T,P) and returns a dictionary mapping job names to shapes.
    """
    jobs = {}
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) != 4:
                raise RuntimeError(f"Incorrect number of columns: {line}")
            name = parts[0]
            dims = tuple(int(x) for x in parts[1:4])
            jobs[name] = dims
    return jobs


def block_placement(torus_blocks, job_blocks, is_random):
    """
    Assigns torus blocks to job blocks randomly and returns a placement dictionary mapping
    job node identifiers to torus node indices.
    """
    job_blocks = dict(sorted(job_blocks.items()))
    placement = {}
    for job_name, j_blocks in job_blocks.items():
        for j_block in j_blocks:
            block_ptr = random.randrange(len(torus_blocks)) if is_random else 0
            t_block = torus_blocks.pop(block_ptr)
            # print(f"Torus block assigned: {t_block} for job {job_name} block: {j_block}")
            for j_node, t_node in zip(j_block, t_block):
                placement[f"{job_name}-{j_node}"] = t_node

    return placement


def firstfit_placement(torus_dims, jobs):
    """
    Uses First-Fit placement policy to allocate jobs.
    """
    placement = {}
    W, L, H = torus_dims
    FF = FirstFit(W, L, H)

    for name, shape in jobs.items():
        mapping = FF.allocate(shape)
        if not mapping:
            raise RuntimeError(f"Failed to place job {name} with shape {shape}.")
        for j_idx in sorted(mapping.keys()):
            placement[f"{name}-{j_idx}"] = mapping[j_idx]

    return placement


def dump(placement, output_path):
    placement = dict(natsorted(placement.items()))
    with open(output_path, "w") as f:
        json.dump(placement, f, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate placement.json file.")
    parser.add_argument(
        "-D",
        "--torus_dims",
        type=lambda s: tuple(int(dim) for dim in s.split("x")),
        default=(4, 4, 4),
        required=True,
        help="Dimension size of an WxLxH Torus.",
    )
    parser.add_argument(
        "-B",
        "--block_size",
        type=int,
        default=2,
        help="Size of an BxBxB block.",
    )
    parser.add_argument(
        "-J",
        "--jobspec",
        type=str,
        required=True,
        help="Path to the jobspec file, which contains job shapes.",
    )
    parser.add_argument(
        "-o", "--output", default="placement.json", help="Output JSON file path."
    )
    parser.add_argument(
        "-P", "--policy", default="firstfit", help="Placement policy to use."
    )
    parser.add_argument(
        "-r", "--random", action="store_true", help="Assign placement randomly."
    )

    args = parser.parse_args()
    # Parse jobspec and construct jobs.
    jobs = parse_jobspec(args.jobspec)

    # Validate that total job size does not exceed torus capacity
    total_job_size = sum(prod(dims) for dims in jobs.values())
    torus_size = prod(args.torus_dims)
    if total_job_size > torus_size:
        raise ValueError(
            f"Error: Total job nodes ({total_job_size}) exceed torus capacity ({torus_size})."
        )

    if args.policy == "firstfit":
        placement = firstfit_placement(args.torus_dims, jobs)
    else:
        # Validate that block size does not exceed the smallest dimension of any job
        for name, dims in jobs.items():
            min_dim = min(dims)
            if args.block_size > min_dim:
                raise ValueError(
                    f"Error: Block size ({args.block_size}) is greater than "
                    f"the smallest dimension ({min_dim}) in job {name} : {dims}."
                )

        torus_blocks = init_torus_blocks(args.torus_dims, args.block_size)
        # print(f"Initialized {len(torus_blocks)} torus blocks:\n{torus_blocks}")
        job_blocks = init_job_blocks(jobs, args.block_size)
        # for name, blocks in job_blocks.items():
        #     print(f"Initialized {len(blocks)} blocks for job {name}:\n{blocks}")
        placement = block_placement(torus_blocks, job_blocks, args.random)

    # print(f"Final Placement:\n{placement}")
    dump(placement, args.output)
