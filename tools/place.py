import argparse
import json
from natsort import natsorted
from math import prod
from placement_lib import FirstFit, SpaceFillingCurve, L1Clustering, BlockRandom


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


def place_with_policy(torus_dims, jobs, policy, block_dims):
    """
    Generate job placement with a policy.
    """
    placement = {}
    W, L, H = torus_dims

    if policy == "firstfit":
        policy_impl = FirstFit(W, L, H)
    elif policy == "sfc":
        policy_impl = SpaceFillingCurve(W, L, H)
    elif policy == "l1clustering":
        policy_impl = L1Clustering(W, L, H)
    elif policy == "random":
        policy_impl = BlockRandom(W, L, H, *block_dims)
    else:
        raise ValueError(f"Unknown placement policy: {policy}")

    for name, shape in jobs.items():
        mapping = policy_impl.allocate(shape)
        if not mapping:
            raise RuntimeError(
                f"[{policy}] Failed to place job {name} with shape {shape}."
            )
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
        "--block_dims",
        type=lambda s: tuple(int(dim) for dim in s.split("x")),
        default=(2, 2, 2),
        required=True,
        help="Dimension size of an BXxBYxBZ block.",
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

    placement = place_with_policy(args.torus_dims, jobs, args.policy, args.block_dims)
    # print(f"Final Placement:\n{placement}")
    dump(placement, args.output)
