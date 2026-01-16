#!/usr/bin/env python3
import argparse
from pathlib import Path


def make_parser():
    parser = argparse.ArgumentParser(prog='myscript', description="Example CLI")
    parser.add_argument("--input", type=Path, help="Input file")
    parser.add_argument("--output", type=Path, help="Output file")
    return parser

def handler(args):
    # do something simple
    args.output.write_text(args.input.read_text().upper())

    # TODO call recorder here

def main():
    parser = make_parser()
    args = parser.parse_args()
    handler(args)

if __name__ == "__main__":
    main()
