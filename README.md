# rocrate-action-recorder

<!-- SPHINX-START -->
[![github repo badge](https://img.shields.io/badge/github-repo-000.svg?logo=github&labelColor=gray&color=blue)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![github license badge](https://img.shields.io/github/license/i-VRESSE/rocrate-action-recorder)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![CI](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml/badge.svg)](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml)
[![readthedocs](https://app.readthedocs.org/projects/rocrate-action-recorder/badge/?version=latest)](https://rocrate-action-recorder.readthedocs.io/en/latest/)

Python package to record calls of Python CLI commands into a [Research Object Crate (RO-Crate)](https://www.researchobject.org/ro-crate/).

Supports [RO-Crate 1.1](https://www.researchobject.org/ro-crate/specification/1.1/index.html) specification.
Specifically the [Process Run Crate profile](https://www.researchobject.org/workflow-run-crate/profiles/0.5/process_run_crate/).

## Install

```shell
pip install rocrate-action-recorder
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

<details>
<summary>
Will generate a `ro-crate-metadata.json` file in the current working directory describing the execution of the CLI command. (Click me to see crate content)
</summary>

```json
{
    "@context": [
        "https://w3id.org/ro/crate/1.1/context",
        "https://w3id.org/ro/terms/workflow-run/context"
    ],
    "@graph": [
        {
            "@id": "./",
            "@type": "Dataset",
            "conformsTo": {
                "@id": "https://w3id.org/ro/wfrun/process/0.5"
            },
            "datePublished": "2026-01-28T15:07:18.600135",
            "description": "An RO-Crate recording the files and directories that were used as input or output by example-cli.",
            "hasPart": [
                {
                    "@id": "input.txt"
                },
                {
                    "@id": "output.txt"
                }
            ],
            "license": "CC-BY-4.0",
            "name": "Files used by example-cli"
        },
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {
                "@id": "./"
            },
            "conformsTo": {
                "@id": "https://w3id.org/ro/crate/1.1"
            }
        },
        {
            "@id": "https://w3id.org/ro/wfrun/process/0.5",
            "@type": "CreativeWork",
            "name": "Process Run Crate",
            "version": "0.5"
        },
        {
            "@id": "example-cli@1.2.3",
            "@type": "SoftwareApplication",
            "description": "Example CLI",
            "name": "example-cli",
            "version": "1.2.3"
        },
        {
            "@id": "input.txt",
            "@type": "File",
            "contentSize": 5,
            "description": "Input file",
            "encodingFormat": "text/plain",
            "name": "input.txt"
        },
        {
            "@id": "output.txt",
            "@type": "File",
            "contentSize": 5,
            "description": "Output file",
            "encodingFormat": "text/plain",
            "name": "output.txt"
        },
        {
            "@id": "someuser",
            "@type": "Person",
            "name": "someuser"
        },
        {
            "@id": "example-cli input.txt output.txt",
            "@type": "CreateAction",
            "agent": {
                "@id": "someuser"
            },
            "endTime": "2026-01-28T15:07:18.600135",
            "instrument": {
                "@id": "example-cli@1.2.3"
            },
            "name": "example-cli input.txt output.txt",
            "object": [
                {
                    "@id": "input.txt"
                }
            ],
            "result": [
                {
                    "@id": "output.txt"
                }
            ],
            "startTime": "2026-01-28T15:07:18.599714"
        }
    ]
}
```

For you the startTime, endTime, and Person name will differ.

</details>

<details>
<summary>
You can also call the argument parser agnostic version of the recorder directly. (Click me to see code)
</summary>

```python
from datetime import datetime, UTC
from pathlib import Path

from rocrate_action_recorder import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    record,
)

crate_dir = Path()
input_path = crate_dir / "input.txt"
output_path = crate_dir / "output.txt"
input_path.write_text("Hello World\n")
argv = [
    "myscript",
    "--input",
    str(input_path),
    "--output",
    str(output_path),
]
start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
# Simulate the script's main operation
output_path.write_text(input_path.read_text().upper())
end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

crate_meta = record(
    program=Program(
        name="myscript", description="My test script", version="1.2.3"
    ),
    ioargs=IOArgumentPaths(
        input_files=[
            IOArgumentPath(name="input", path=input_path, help="Input file")
        ],
        output_files=[
            IOArgumentPath(name="output", path=output_path, help="Output file")
        ],
    ),
    argv=argv,
    current_user="tester",
    start_time=start_time,
    end_time=end_time,
    crate_dir=crate_dir,
    dataset_license="CC-BY-4.0",
)
# crate_meta == Path("ro-crate-metadata.json")
```

</details>

<!-- SPHINX-END -->

## Example

See the [example](example/README.md) folder for a minimal example.

### Contributions

See [AGENTS.md](AGENTS.md) for commands and hints for contributions.

### Citation

See [CITATION.cff](CITATION.cff) for citation information.
