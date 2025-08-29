import random
import argparse
import math
import re
from typing import List


def generate_torus_links(dims: List[int], bandwidth: str, latency: str):
    """
    Generates the header lines and links for a grid or torus network topology.
    Returns (header_line1, header_line2, links)
    """
    num_dims = len(dims)
    if not (1 <= num_dims <= 3):
        raise ValueError("Only 1D, 2D, or 3D topologies are supported.")

    total_nodes = math.prod(dims)
    if total_nodes <= 0:
        raise ValueError("The product of the dimensions must be positive.")

    links = []
    seen_links = set()

    for node_id in range(total_nodes):
        coords = []
        temp_id = node_id
        for i in range(num_dims - 1, -1, -1):
            base = math.prod(dims[0:i])
            coord = temp_id // base
            coords.insert(0, coord)
            temp_id %= base

        for i in range(num_dims):
            dim_size = dims[i]
            current_pos_in_dim = coords[i]
            is_wrap_around_link = current_pos_in_dim == dim_size - 1
            if is_wrap_around_link and dim_size < 3:
                continue
            neighbor_coords = list(coords)
            neighbor_coords[i] = (current_pos_in_dim + 1) % dim_size
            neighbor_id = 0
            multiplier = 1
            for j in range(num_dims):
                neighbor_id += neighbor_coords[j] * multiplier
                multiplier *= dims[j]
            link_pair = tuple(sorted((node_id, neighbor_id)))
            if link_pair not in seen_links:
                link_str = f"{node_id} {neighbor_id} {bandwidth} {latency} 0"
                links.append(link_str)
                seen_links.add(link_pair)

    total_links = len(links)
    header_line1 = f"{total_nodes} 0 {total_links}"
    header_line2 = ""
    return header_line1, header_line2, links


def write_torus_topology_file(
    output_file: str, header_line1: str, header_line2: str, links: list
):
    """
    Writes the torus topology to a file given header lines and links.
    """
    try:
        with open(output_file, "w") as f:
            f.write(header_line1 + "\n")
            f.write(header_line2 + "\n")
            f.write(
                "\n".join(sorted(links, key=lambda l: tuple(map(int, l.split()[:2]))))
            )
    except IOError as e:
        print(f"Error writing to file {output_file}: {e}")


def model_contention(links: list, n_links: int, m_jobs: int) -> list:
    """
    For n_links randomly chosen from links, divide their bandwidth by m_jobs.
    Args:
        links (list): List of link strings (e.g., '0 1 400Gbps 0.001ms 0').
        n_links (int): Number of links to apply contention to.
        m_jobs (int): Number of jobs to divide bandwidth by.
    Returns:
        list: Modified links list with bandwidth divided for selected links.
    """
    if n_links > len(links):
        raise ValueError("n_links cannot be greater than the number of links.")
    selected_indices = random.sample(range(len(links)), n_links)
    modified_links = links.copy()
    for idx in selected_indices:
        parts = modified_links[idx].split()
        bw = parts[2]
        # Extract numeric value and unit
        match = re.match(r"([0-9.]+)([A-Za-z]+)", bw)
        if not match:
            raise ValueError(f"Unrecognized bandwidth format: {bw}")
        value, unit = match.groups()
        new_value = float(value) / m_jobs
        # Format with up to 6 decimal places, strip trailing zeros
        new_bw = (
            f"{new_value:.6f}".rstrip("0").rstrip(".")
            if "." in f"{new_value:.6f}"
            else str(new_value)
        ) + unit
        parts[2] = new_bw
        modified_links[idx] = " ".join(parts)
    return modified_links


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a 1D, 2D, or 3D grid/torus network topology file.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--dims",
        nargs="+",
        type=int,
        required=True,
        help="A list of integers for the dimensions of the topology.\n"
        "Example for 1D: --dims 8\n"
        "Example for 2D: --dims 4 4\n"
        "Example for 3D: --dims 3 3 2",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="The name of the output file (e.g., 'torus_4x4.txt').",
    )
    parser.add_argument(
        "-b",
        "--bandwidth",
        type=str,
        default="400Gbps",
        help="Bandwidth for all links (e.g., '400Gbps'). Default: 400Gbps.",
    )
    parser.add_argument(
        "-l",
        "--latency",
        type=str,
        default="0.001ms",
        help="Latency for all links (e.g., '0.001ms'). Default: 0.001ms.",
    )

    args = parser.parse_args()
    try:
        header_line1, header_line2, links = generate_torus_links(
            args.dims, args.bandwidth, args.latency
        )
        write_torus_topology_file(args.output, header_line1, header_line2, links)
        dimension_str = "x".join(map(str, args.dims))
        print(f"Successfully generated topology for a {dimension_str}.")
        print(f"- Total Nodes: {header_line1.split()[0]}")
        print(f"- Total Links: {header_line1.split()[2]}")
        print(f"- Bandwidth: {args.bandwidth} | Latency: {args.latency}")
        print(f"- Output File: {args.output}")
    except ValueError as e:
        print(f"Error: {e}")
