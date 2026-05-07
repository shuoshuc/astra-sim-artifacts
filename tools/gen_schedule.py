#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate per-topology bandwidth and latency matrices for the analytical
reconfigurable backend. Each matrix is an N x N adjacency matrix over NPU
pairs (N = X * Y * Z). Non-neighbor pairs get 0; direct neighbors (with
torus wrap-around) get the supplied bandwidth or latency value.

Usage:
    python gen_schedule.py -x 2 -y 2 -z 1 -bw 50 -lt 500 \\
        --bw-output bw_schedule.txt \\
        --latency-output latency_schedule.txt
"""

import argparse
import csv
from pathlib import Path
from itertools import product

import numpy as np


def generate_schedule(bw, lt, X, Y, Z):
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
        for nbr in (
            coord_to_index((a + 1) % X, b, c),
            coord_to_index(a, (b + 1) % Y, c),
            coord_to_index(a, b, (c + 1) % Z),
        ):
            if idx != nbr:
                bw_matrix[idx, nbr] = bw
                bw_matrix[nbr, idx] = bw
                lt_matrix[idx, nbr] = lt
                lt_matrix[nbr, idx] = lt

    return bw_matrix.tolist(), lt_matrix.tolist()


def write_matrix(path, matrix, tag, topo_id=0):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as f:
        writer = csv.writer(f, delimiter=" ")
        writer.writerow([tag, topo_id])
        for row in matrix:
            writer.writerow(row)
        writer.writerow(["END"])


def main():
    parser = argparse.ArgumentParser(
        description="Generate paired bandwidth and latency schedule files."
    )
    parser.add_argument("-bw", "--bandwidth", type=float, default=50.0,
                        help="Per-link bandwidth in GB/s (default 50.0).")
    parser.add_argument("-lt", "--latency", type=float, default=500.0,
                        help="Per-link latency in ns (default 500.0).")
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

    bw_matrix, lt_matrix = generate_schedule(
        args.bandwidth, args.latency,
        args.x_dim, args.y_dim, args.z_dim,
    )
    write_matrix(args.bw_output, bw_matrix, "BW")
    write_matrix(args.latency_output, lt_matrix, "LT")


if __name__ == "__main__":
    main()
