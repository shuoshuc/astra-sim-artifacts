import argparse
import itertools
import json
import random
from math import prod


def init_torus_blocks(N, B):
    """
    Initialize a list of lists, where each list contains node indices of a BxBxB block in an NxNxN torus.
    Nodes in the torus are indexed in plane-major order.
    """
    if N % B != 0:
        raise ValueError("Block size must divide torus size exactly.")

    blocks = []
    for z_start, y_start, x_start in itertools.product(range(0, N, B), repeat=3):
        block = []
        for z, y, x in itertools.product(
            range(z_start, z_start + B),
            range(y_start, y_start + B),
            range(x_start, x_start + B),
        ):
            block.append(z * (N**2) + y * N + x)
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


def assign_placement(torus_blocks, job_blocks, is_random):
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


def dump(placement, output_path):
    placement = dict(
        sorted(
            placement.items(),
            key=lambda item: (
                item[0].split("-")[0],
                int(item[0].split("-")[1]),
            ),
        )
    )
    with open(output_path, "w") as f:
        json.dump(placement, f, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate placement.json file.")
    parser.add_argument(
        "-N",
        "--torus_size",
        type=int,
        required=True,
        default=4,
        help="Size of an NxNxN Torus.",
    )
    parser.add_argument(
        "-B",
        "--block_size",
        type=int,
        required=True,
        default=2,
        help="Size of an BxBxB block.",
    )
    parser.add_argument(
        "-o", "--output", default="placement.json", help="Output JSON file path."
    )
    parser.add_argument(
        "-r", "--random", action="store_true", help="Assign placement randomly."
    )

    class JobShapesAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            jobs = {}
            for v in values.split(","):
                try:
                    name, shape = v.split(":")
                    dims = [int(d) for d in shape.split("x") if d]
                    jobs[name] = dims
                except Exception:
                    parser.error(f"Invalid job shape '{v}'. Expected Name:AxBxC...")
            setattr(namespace, "jobs", jobs)

    parser.add_argument(
        "-J",
        "--jobs",
        action=JobShapesAction,
        help="Specify jobs by shape as Name:AxBxC (comma separated).",
    )

    args = parser.parse_args()
    # Validate that block size does not exceed the smallest dimension of any job
    for name, dims in args.jobs.items():
        min_dim = min(dims)
        if args.block_size > min_dim:
            raise ValueError(
                f"Error: Block size ({args.block_size}) is greater than "
                f"the smallest dimension ({min_dim}) in job {name} : {dims}."
            )
    # Validate that total job size does not exceed torus capacity
    total_job_size = sum(prod(dims) for dims in args.jobs.values())
    torus_size = args.torus_size**3
    if total_job_size > torus_size:
        raise ValueError(
            f"Error: Total job nodes ({total_job_size}) exceed torus capacity ({torus_size})."
        )

    torus_blocks = init_torus_blocks(args.torus_size, args.block_size)
    # print(f"Initialized {len(torus_blocks)} torus blocks:\n{torus_blocks}")
    job_blocks = init_job_blocks(args.jobs, args.block_size)
    # for name, blocks in job_blocks.items():
    #     print(f"Initialized {len(blocks)} blocks for job {name}:\n{blocks}")
    placement = assign_placement(torus_blocks, job_blocks, args.random)
    # print(f"Final Placement:\n{placement}")
    dump(placement, args.output)
