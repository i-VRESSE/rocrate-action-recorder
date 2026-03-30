#!/usr/bin/env python3

from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from rocrate_action_recorder.adapters.cyclopts import (
    INPUT_FILE,
    OUTPUT_FILE,
    RECORD_TRIGGER,
    run_with_record,
)


app = App(
    version="1.0.0",
)


@app.default
def main(
    input: Annotated[Path, INPUT_FILE],
    output: Annotated[Path, OUTPUT_FILE],
    /,
    *,
    prov: Annotated[
        bool,
        Parameter(negative=""),
        RECORD_TRIGGER,
    ] = False,
):
    """Uppercase the contents of the input file and write to the output file.

    Args:
        input: The input file to read from.
        output: The output file to write to.
        prov: Whether to record provenance information.

    Returns:
        The number of characters written to the output file.
    """
    print(f"Provenance recording is {'enabled' if prov else 'disabled'}.")
    return output.write_text(input.read_text().upper())


if __name__ == "__main__":
    run_with_record(app, dataset_license="CC-BY-4.0")
