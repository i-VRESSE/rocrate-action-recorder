#!/usr/bin/env python3
import argparse
from datetime import datetime
from pathlib import Path
from rocrate_action_recorder import record_with_argparse, IOs


def make_parser():
    parser = argparse.ArgumentParser(prog="myscript", description="Example CLI")
    parser.add_argument("--input", type=Path, help="Input file")
    parser.add_argument("--output", type=Path, help="Output file")
    return parser


def handler(args, parser):
    start_time = datetime.now()
    # do something simple
    args.output.write_text(args.input.read_text().upper())

    ios = IOs(input_files=["input"], output_files=["output"])
    record_with_argparse(
        parser=parser,
        ns=args,
        ios=ios,
        start_time=start_time,
    )


def main():
    parser = make_parser()
    args = parser.parse_args()
    handler(args, parser)


if __name__ == "__main__":
    main()
