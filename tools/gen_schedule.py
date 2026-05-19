#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate per-topology bandwidth and latency matrices for the analytical
reconfigurable backend. Each matrix is an N x N adjacency matrix over NPU
pairs (N = X * Y * Z). Non-neighbor pairs get 0; direct neighbors (with
torus wrap-around) get the supplied bandwidth or latency value.

`-bw` and `-lt` accept either a scalar (same value on every dim) or a
comma-separated 3-element list giving per-dimension values in X,Y,Z order.
The list must always have length 3 even when a dim is 1 (the entry for the
degenerate dim is parsed but unused).

Usage (scalar, backward-compatible):
    python gen_schedule.py -x 16 -y 16 -z 16 -bw 50 -lt 500 \\
        --bw-output bw_schedule.txt \\
        --latency-output latency_schedule.txt

Usage (per-dim):
    python gen_schedule.py -x 2 -y 2 -z 1 \\
        -bw 25,50,50 -lt 1000,500,500 \\
        --bw-output bw_schedule.txt \\
        --latency-output latency_schedule.txt
"""

import argparse
import csv
from pathlib import Path
from itertools import product

import numpy as np


def parse_per_dim(raw: str, flag_name: str) -> list[float]:
    """Parse a scalar or 3-element comma-separated list into a length-3 list."""
    parts = [p.strip() for p in raw.split(",")]
    try:
        values = [float(p) for p in parts]
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"{flag_name}: could not parse {raw!r} as numeric value(s): {e}"
        )
    if len(values) == 1:
        return [values[0]] * 3
    if len(values) == 3:
        return values
    raise argparse.ArgumentTypeError(
        f"{flag_name}: expected scalar or 3-element comma list, "
        f"got {len(values)} elements ({raw!r})"
    )


def generate_schedule(
    bw_per_dim: list[float],
    lt_per_dim: list[float],
    X: int,
    Y: int,
    Z: int,
) -> tuple[list[list[float]], list[list[float]]]:
    """Return (bw_matrix, lt_matrix) as nested Python lists.

    1D linearization is X-fastest:
        idx = a + b*X + c*X*Y
    matching precomputeRoutes_DOR() in TopologyManager.cpp.
    """
    N = X * Y * Z
    bw_matrix = np.zeros((N, N), dtype=float)
    lt_matrix = np.zeros((N, N), dtype=float)

    def coord_to_index(a, b, c):
        return a + (b * X) + (c * X * Y)

    for a, b, c in product(range(X), range(Y), range(Z)):
        idx = coord_to_index(a, b, c)
        neighbors = [
            (coord_to_index((a + 1) % X, b, c), bw_per_dim[0], lt_per_dim[0]),
            (coord_to_index(a, (b + 1) % Y, c), bw_per_dim[1], lt_per_dim[1]),
            (coord_to_index(a, b, (c + 1) % Z), bw_per_dim[2], lt_per_dim[2]),
        ]
        for nbr, bw_v, lt_v in neighbors:
            if idx != nbr:
                bw_matrix[idx, nbr] = bw_v
                bw_matrix[nbr, idx] = bw_v
                lt_matrix[idx, nbr] = lt_v
                lt_matrix[nbr, idx] = lt_v

    return bw_matrix.tolist(), lt_matrix.tolist()


def write_matrix(path: str, matrix: list[list[float]], tag: str, topo_id: int = 0) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        writer = csv.writer(f, delimiter=" ", lineterminator="\n")
        writer.writerow([tag, topo_id])
        for row in matrix:
            writer.writerow(row)
        writer.writerow(["END"])


def main():
    parser = argparse.ArgumentParser(
        description="Generate paired bandwidth and latency schedule files."
    )
    parser.add_argument(
        "-bw", "--bandwidth", default="50",
        help="Per-link bandwidth in GB/s. Scalar or 3-element X,Y,Z list "
             "(default 50).",
    )
    parser.add_argument(
        "-lt", "--latency", default="500",
        help="Per-link latency in ns. Scalar or 3-element X,Y,Z list "
             "(default 500).",
    )
    parser.add_argument("-x", "--x_dim", type=int, default=1,
                        help="Torus X dimension.")
    parser.add_argument("-y", "--y_dim", type=int, default=1,
                        help="Torus Y dimension.")
    parser.add_argument("-z", "--z_dim", type=int, default=1,
                        help="Torus Z dimension.")
    parser.add_argument("--bw-output", required=True,
                        help="Output path for the BW schedule file.")
    parser.add_argument("--latency-output", required=True,
                        help="Output path for the LT schedule file.")
    args = parser.parse_args()

    bw_per_dim = parse_per_dim(args.bandwidth, "-bw")
    lt_per_dim = parse_per_dim(args.latency, "-lt")

    bw_matrix, lt_matrix = generate_schedule(
        bw_per_dim, lt_per_dim,
        args.x_dim, args.y_dim, args.z_dim,
    )
    write_matrix(args.bw_output, bw_matrix, "BW")
    write_matrix(args.latency_output, lt_matrix, "LT")


if __name__ == "__main__":
    main()
