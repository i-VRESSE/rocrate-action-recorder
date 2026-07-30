# rocrate-action-recorder

<!-- SPHINX-START -->
[![PyPI](https://img.shields.io/pypi/v/rocrate-action-recorder)](https://pypi.org/project/rocrate-action-recorder/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19364813.svg)](https://doi.org/10.5281/zenodo.19364813)
[![Research Software Directory Badge](https://img.shields.io/badge/rsd-00a3e3.svg)](https://research-software-directory.org/software/rocrate-action-recorder)
[![github repo badge](https://img.shields.io/badge/github-repo-000.svg?logo=github&labelColor=gray&color=blue)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![github license badge](https://img.shields.io/github/license/i-VRESSE/rocrate-action-recorder)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![CI](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml/badge.svg)](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml)
[![readthedocs](https://app.readthedocs.org/projects/rocrate-action-recorder/badge/?version=latest)](https://rocrate-action-recorder.readthedocs.io/en/latest/)


Python package to record calls of Python CLI commands into a [Research Object Crate (RO-Crate)](https://www.researchobject.org/ro-crate/).
Useful to track which commands were executed, which files were used as input or output, and which software was used to execute the command.

Supports [RO-Crate 1.1](https://www.researchobject.org/ro-crate/specification/1.1/index.html) specification.
Specifically the [Process Run Crate profile](https://www.researchobject.org/workflow-run-crate/profiles/0.5/process_run_crate/).

Provides adapters for CLIs based on (links go to examples)

* [argparse](https://github.com/i-VRESSE/rocrate-action-recorder/tree/main/example/argparse)
* [click](https://github.com/i-VRESSE/rocrate-action-recorder/tree/main/example/click)
* [cyclopts](https://github.com/i-VRESSE/rocrate-action-recorder/tree/main/example/cyclopts)

## Install

```shell
pip install rocrate-action-recorder
```

For [Click](https://click.palletsprojects.com/en/stable/) support, install the optional extra:

```shell
pip install "rocrate-action-recorder[click]"
```

For [Cyclopts](https://github.com/BrianPugh/cyclopts) support, install the optional extra:

```shell
pip install "rocrate-action-recorder[cyclopts]"
```

## Usage

Example of recording a CLI command (`example-cli input.txt output.txt`) implemented with `argparse`.

```python
import argparse
from pathlib import Path
import sys

from rocrate_action_recorder import recorded_argparse

parser = argparse.ArgumentParser(prog="example-cli", description="Example CLI")
parser.add_argument("--version", action="version", version="%(prog)s 1.2.3")
parser.add_argument("--no-record", action="store_false", help="Disable RO-Crate recording.")
parser.add_argument("input", type=Path, help="Input file")
parser.add_argument("output", type=Path, help="Output file")


@recorded_argparse(
    parser=parser,
    input_files=["input"],
    output_files=["output"],
    dataset_license="CC-BY-4.0",
    enabled_argument="no_record",
)
def handler(args: argparse.Namespace):
    # For demonstration, just upper case input to output, replace with real logic
    args.output.write_text(args.input.read_text().upper())


# Prepare input
Path("input.txt").write_text("hello")
# Simulate command-line arguments
sys.argv.extend(["input.txt", "output.txt"])

args = parser.parse_args()
handler(args)
```

After execution, a `ro-crate-metadata.json` file (like [this one](https://github.com/i-VRESSE/rocrate-action-recorder/blob/main/example/argparse/ro-crate-metadata.json)) will be generated in the current working directory, describing the execution of the CLI command.

<!-- SPHINX-END -->

You can also call the low-level [record](https://rocrate-action-recorder.readthedocs.io/en/latest/autoapi/rocrate_action_recorder/core/index.html#rocrate_action_recorder.core.record) function directly. 

See [documentation](https://rocrate-action-recorder.readthedocs.io/en/latest/) for more details.

### Contributions

See [AGENTS.md](AGENTS.md) for commands and hints for contributions.

### Citation

See [CITATION.cff](CITATION.cff) for citation information.
