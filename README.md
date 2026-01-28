# rocrate-action-recorder

[![github repo badge](https://img.shields.io/badge/github-repo-000.svg?logo=github&labelColor=gray&color=blue)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![github license badge](https://img.shields.io/github/license/i-VRESSE/rocrate-action-recorder)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![CI](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml/badge.svg)](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml)

Python package to record calls of Python CLI commands into a [Research Object Crate (RO-Crate)](https://www.researchobject.org/ro-crate/).

Supports [RO-Crate 1.1](https://www.researchobject.org/ro-crate/specification/1.1/index.html) specification.
Specifically the [Process Run Crate profile](https://www.researchobject.org/workflow-run-crate/profiles/0.5/process_run_crate/).

## Install

```shell
pip install rocrate-action-recorder
```

## Usage

```python
import argparse
from datetime import datetime
from pathlib import Path
from rocrate_action_recorder import record_with_argparse, IOs

parser = argparse.ArgumentParser(prog="example-cli", description="Example CLI")
parser.add_argument("--version", action="version", version="1.2.3")
parser.add_argument("input", type=Path, help="Input file")
parser.add_argument("output", type=Path, help="Output file")

Path("input.txt").write_text("hello")
args = ['input.txt', 'output.txt']
ns = parser.parse_args(args)
# Tell recorder about input and output files
ios = IOs(input_files=["input"], output_files=["output"])
start_time = datetime.now()

# Do handling of the CLI command here...
# For demonstration, just upper case input to output
Path(ns.output).write_text(ns.input.read_text().upper())

record_with_argparse(
    parser, ns, ios, 
    start_time, 
    dataset_license="CC-BY-4.0",
    # argv argument is optional, in real usage you can omit it
    argv=['example-cli'] + args,
    # current_user argument is optional, in real usage you can omit it
    current_user="someuser"
)
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

</details>

## Example

See the [example](example/) folder for a minimal example.

### Contributions

See [AGENTS.md](AGENTS.md) for commands and hints for contributions.
