import argparse
import math
from typing import List

def generate_torus_topology(dims: List[int], output_file: str, bandwidth: str, latency: str):
    """
    Generates a grid or torus network topology file.

    Node Numbering: Nodes are numbered left-to-right, top-to-bottom (row-major order).
    Wrap-around Links: Links that connect the ends of a dimension to form a torus
    are only added if the size of that dimension is 3 or more. Otherwise, it
    remains a simple grid along that axis.

    Args:
        dims (List[int]): A list of integers for the dimensions (1D, 2D, or 3D).
        output_file (str): The path to the output file.
        bandwidth (str): The bandwidth for all links (e.g., '100Gbps').
        latency (str): The latency for all links (e.g., '0.01ms').
    """
    num_dims = len(dims)
    if not (1 <= num_dims <= 3):
        raise ValueError("Only 1D, 2D, or 3D topologies are supported.")

    # Calculate total number of nodes
    total_nodes = math.prod(dims)
    if total_nodes <= 0:
        raise ValueError("The product of the dimensions must be positive.")

    links = []
    seen_links = set()

    # --- Link Generation ---
    for node_id in range(total_nodes):
        # --- Calculate N-dimensional coordinates from a 1D node ID (row-major) ---
        coords = []
        temp_id = node_id
        for i in range(num_dims - 1, -1, -1):
            base = math.prod(dims[0:i])
            coord = temp_id // base
            coords.insert(0, coord)
            temp_id %= base

        # --- For each dimension, create links to the "next" node ---
        for i in range(num_dims):
            dim_size = dims[i]
            current_pos_in_dim = coords[i]
            is_wrap_around_link = (current_pos_in_dim == dim_size - 1)

            # RULE: Only add wrap-around links if the dimension size is 3 or more.
            if is_wrap_around_link and dim_size < 3:
                continue

            # --- If the link should be created, find the neighbor ---
            neighbor_coords = list(coords)
            neighbor_coords[i] = (current_pos_in_dim + 1) % dim_size

            # --- Convert neighbor's N-D coordinates back to a 1D ID ---
            neighbor_id = 0
            multiplier = 1
            for j in range(num_dims):
                neighbor_id += neighbor_coords[j] * multiplier
                multiplier *= dims[j]

            # Ensure the link is not duplicated
            link_pair = tuple(sorted((node_id, neighbor_id)))
            if link_pair not in seen_links:
                # Use the provided bandwidth and latency parameters
                link_str = f"{node_id} {neighbor_id} {bandwidth} {latency} 0"
                links.append(link_str)
                seen_links.add(link_pair)

    # --- Header Information ---
    total_links = len(links)
    header_line1 = f"{total_nodes} 0 {total_links}"
    header_line2 = ""

    # --- Write to Output File ---
    try:
        with open(output_file, 'w') as f:
            f.write(header_line1 + '\n')
            f.write(header_line2 + '\n')
            f.write('\n'.join(sorted(links, key=lambda l: tuple(map(int, l.split()[:2])))))

        dimension_str = 'x'.join(map(str, dims))
        print(f"Successfully generated topology for a {dimension_str}.")
        print(f"- Total Nodes: {total_nodes}")
        print(f"- Total Links: {total_links}")
        print(f"- Bandwidth: {bandwidth} | Latency: {latency}")
        print(f"- Output File: {output_file}")

    except IOError as e:
        print(f"Error writing to file {output_file}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a 1D, 2D, or 3D grid/torus network topology file.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--dims',
        nargs='+',
        type=int,
        required=True,
        help="A list of integers for the dimensions of the topology.\n"
             "Example for 1D: --dims 8\n"
             "Example for 2D: --dims 4 4\n"
             "Example for 3D: --dims 3 3 2"
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        required=True,
        help="The name of the output file (e.g., 'torus_4x4.txt')."
    )
    parser.add_argument(
        '-b', '--bandwidth',
        type=str,
        default='400Gbps',
        help="Bandwidth for all links (e.g., '400Gbps'). Default: 400Gbps."
    )
    parser.add_argument(
        '-l', '--latency',
        type=str,
        default='0.001ms',
        help="Latency for all links (e.g., '0.001ms'). Default: 0.001ms."
    )

    args = parser.parse_args()
    try:
        generate_torus_topology(args.dims, args.output, args.bandwidth, args.latency)
    except ValueError as e:
        print(f"Error: {e}")
