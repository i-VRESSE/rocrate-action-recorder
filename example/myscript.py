#!/usr/bin/env python3
import argparse
from datetime import datetime
from pathlib import Path
import rocrate_action_recorder


def make_parser():
    parser = argparse.ArgumentParser(prog='myscript', description="Example CLI")
    parser.add_argument("--input", type=Path, help="Input file")
    parser.add_argument("--output", type=Path, help="Output file")
    return parser

def handler(args, parser):
    start_time = datetime.now()
    # do something simple
    args.output.write_text(args.input.read_text().upper())

    rocrate_action_recorder.record(
        args=args,
        inputs=['input'],
        outputs=['output'],
        parser=parser,
        start_time=start_time,
    )

def main():
    parser = make_parser()
    args = parser.parse_args()
    handler(args, parser)

if __name__ == "__main__":
    main()
