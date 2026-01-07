import argparse
from math import prod


def create_jobspec(args, bg_shape):
    job_list = [] + args.jobs
    total_nodes = prod(args.torus_dims)
    assigned_nodes = sum(prod(shape) for shape in job_list)
    if assigned_nodes > total_nodes:
        raise RuntimeError(
            f"Total job nodes ({assigned_nodes}) exceed torus capacity ({total_nodes})."
        )
    while total_nodes > assigned_nodes:
        job_list.append(bg_shape)
        assigned_nodes += prod(bg_shape)
    if assigned_nodes != total_nodes:
        raise RuntimeError(
            f"Total job nodes ({assigned_nodes}) do not fully use capacity ({total_nodes})."
        )

    # Write jobspec to file.
    with open(args.output, "w") as f:
        for i, shape in enumerate(job_list):
            dims = ",".join(map(str, shape))
            f.write(f"J{i},{dims}\n")


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate jobspec.")
    parser.add_argument(
        "-D",
        "--torus_dims",
        type=lambda s: tuple(int(dim) for dim in s.split("x")),
        default=(4, 4, 4),
        required=True,
        help="Dimension size of an WxLxH Torus.",
    )

    class JobShapesAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            jobs = []
            for v in values.split(","):
                dims = tuple(int(d) for d in v.split("x"))
                jobs.append(dims)
            setattr(namespace, "jobs", jobs)

    parser.add_argument(
        "-J",
        "--jobs",
        action=JobShapesAction,
        help="Specify jobs by shape as AxBxC (comma separated).",
        required=True,
    )
    parser.add_argument(
        "-b",
        "--bg_shape",
        type=lambda s: tuple(int(dim) for dim in s.split("x")),
        default=(1, 1, 1),
        help="Background job shape.",
    )
    parser.add_argument("-o", "--output", default="jobspec.txt", help="Output file path.")

    args = parser.parse_args()
    create_jobspec(args, args.bg_shape)
