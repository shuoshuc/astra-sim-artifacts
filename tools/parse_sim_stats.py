#!/usr/bin/env python3
import re
import csv
import sys
import argparse
from collections import defaultdict

def parse_astra_logs(input_path, output_path):
    """
    Parses astra sim output statistics.
    Searches for lines that are formatted like "[timestamp] [statistics] [info] sys[2], Wall time: 17162737840"
    Args:
        input_path (str): path to the log file 
        output_path (str): path to the output csv file
    """
    pattern = re.compile(r"sys\[(\d+)\], ([\w\s-]+): ([\d.]+)")

    # Parse lines
    stats = defaultdict(dict)
    with open(input_path, "r") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                sys_id, metric, value = match.groups()
                metric = metric.strip()
                value = float(value) if "." in value else int(value)
                stats[sys_id][metric] = value

    all_metrics = sorted({m for s in stats.values() for m in s})

    # Write CSV
    with open(output_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        header = ["sys_id"] + all_metrics
        writer.writerow(header)

        for sys_id, metrics in sorted(stats.items(), key=lambda x: int(x[0])):
            row = [sys_id] + [metrics.get(m, "") for m in all_metrics]
            writer.writerow(row)

    print(f"Parsed {len(stats)} nodes. CSV saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Parse Astra-sim output logs into CSV format. (You should pipe Astra-sim's logs into a file)")
    parser.add_argument("--input", required=True, help="Path to Astra-sim output log file (e.g. log.txt)")
    parser.add_argument("--output", required=True, help="Path to save parsed CSV file (e.g. stats.csv)")
    args = parser.parse_args()

    parse_astra_logs(args.input, args.output)


if __name__ == "__main__":
    main()
