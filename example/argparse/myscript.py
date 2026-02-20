#!/usr/bin/env python3
import argparse
from functools import lru_cache
from pathlib import Path
from rocrate_action_recorder import recorded_argparse


@lru_cache(
    maxsize=1
)  # Cache the parser instance to avoid re-creating it for each handler
def make_parser():
    parser = argparse.ArgumentParser(prog="myscript", description="Example CLI")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    parser.add_argument("input", type=Path, help="Input file")
    parser.add_argument("output", type=Path, help="Output file")
    return parser


@recorded_argparse(
    parser=make_parser(),
    input_files=["input"],
    output_files=["output"],
    dataset_license="CC-BY-4.0",
)
def handler(args: argparse.Namespace) -> int:
    # do something simple
    return args.output.write_text(args.input.read_text().upper())


def main():
    parser = make_parser()
    args = parser.parse_args()
    handler(args)


if __name__ == "__main__":
    main()
