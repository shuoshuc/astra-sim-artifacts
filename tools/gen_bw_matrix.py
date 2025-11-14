#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate a bandwidth matrix file for the analytical reconfigurable backend.
The bandwidth matrix decribes the bandwidth between each pair of NPUs as an adjacency matrix.

Usage:
    python gen_bw_matrix.py -x 2 -y 2 -z 1 -d 2 -o schedule.txt

This will generate a bandwidth matrix for a 2x2x1 torus topology with bidirectional links.
"""

import argparse
import csv
import numpy as np
from pathlib import Path
from itertools import product


def generate_bw_matrix(bw: float, X: int, Y: int, Z: int) -> list[list[float]]:
    """
    Creates an N x N bandwidth matrix for a 3D torus.
    
    N = X * Y * Z. The matrix entries are 0, except for directly
    connected neighbors, which are set to 'bandwidth'.
    
    Args:
        bw (float): The bandwidth (in GBps) for a direct link (e.g., 50.0).
        X (int): Dimension of the torus in the x-direction.
        Y (int): Dimension of the torus in the y-direction.
        Z (int): Dimension of the torus in the z-direction.
        
    Returns:
        An N x N bandwidth matrix.
    """
    N = X * Y * Z
    # Initialize an N x N matrix with all zeros
    matrix = np.zeros((N, N), dtype=float)

    # This nested function provides a consistent mapping from
    # (a, b, c) coordinates to a single matrix index i.
    def coord_to_index(a, b, c):
        """Maps 3D coordinate to 1D matrix index."""
        # This is a standard "plane-major" ordering
        return (c * X * Y) + (b * X) + a
    
    # Iterate through every node in the 3D torus
    for a, b, c in product(range(X), range(Y), range(Z)):
        # Get the 1D index for the current node
        idx = coord_to_index(a, b, c)
        
        # Find neighbors. We only need to look in the "+1" direction
        # for each dimension. The (node, neighbor) and (neighbor, node)
        # connections will both be set, ensuring a symmetric matrix.
        #
        # 1. X-dimension neighbor (with wrap-around)
        # (a + 1) % X handles the torus connection
        neighbor_x_idx = coord_to_index((a + 1) % X, b, c)
        if idx != neighbor_x_idx:
            matrix[idx, neighbor_x_idx] = bw
            matrix[neighbor_x_idx, idx] = bw
        # 2. Y-dimension neighbor (with wrap-around)
        neighbor_y_idx = coord_to_index(a, (b + 1) % Y, c)
        if idx != neighbor_y_idx:
            matrix[idx, neighbor_y_idx] = bw
            matrix[neighbor_y_idx, idx] = bw
        # 3. Z-dimension neighbor (with wrap-around)
        neighbor_z_idx = coord_to_index(a, b, (c + 1) % Z)
        if idx != neighbor_z_idx:
            matrix[idx, neighbor_z_idx] = bw
            matrix[neighbor_z_idx, idx] = bw
                

    return matrix.tolist()


def write_matrix(path: str, matrix: list[list[float]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f, delimiter=' ')
        writer.writerow(["BW", 0])
        for row in matrix:
            writer.writerow(row)
        writer.writerow(["END"])


def main():
    parser = argparse.ArgumentParser(description="Generate a bandwidth matrix (txt).")
    parser.add_argument(
        "-bw", "--bandwidth", help="Bandwidth (in GBps) for each link.",
        type=float, default=50.0,
    )
    parser.add_argument(
        "-x", "--x_dim", help="X dimension size of the topology (assuming torus).",
        type=int, default=1,
    )
    parser.add_argument(
        "-y", "--y_dim", help="Y dimension size of the topology (assuming torus).",
        type=int, default=1,
    )
    parser.add_argument(
        "-z", "--z_dim", help="Z dimension size of the topology (assuming torus).",
        type=int, default=1,
    )
    parser.add_argument("-o", "--output", help="Path to the generated bandwidth matrix.")
    args = parser.parse_args()

    mat = generate_bw_matrix(args.bandwidth, args.x_dim, args.y_dim, args.z_dim)
    write_matrix(args.output, mat)


if __name__ == "__main__":
    main()