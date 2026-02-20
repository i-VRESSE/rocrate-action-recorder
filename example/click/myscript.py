#!/usr/bin/env python3
from pathlib import Path

import click

from rocrate_action_recorder import recorded_click


@click.command(help="Example Click CLI")
@click.version_option("1.0.0")
@click.argument("input", type=click.Path(path_type=Path, exists=True))
@click.argument("output", type=click.Path(path_type=Path))
@recorded_click(
    input_files=["input"],
    output_files=["output"],
    dataset_license="CC-BY-4.0",
)
def cli(input: Path, output: Path) -> int:
    return output.write_text(input.read_text().upper())


if __name__ == "__main__":
    cli()
