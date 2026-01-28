# rocrate-action-recorder

[![github repo badge](https://img.shields.io/badge/github-repo-000.svg?logo=github&labelColor=gray&color=blue)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![github license badge](https://img.shields.io/github/license/i-VRESSE/rocrate-action-recorder)](https://github.com/i-VRESSE/rocrate-action-recorder)
[![CI](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml/badge.svg)](https://github.com/i-VRESSE/rocrate-action-recorder/actions/workflows/ci.yml)

Python package to record calls of Python CLI commands into a [Research Object Crate (RO-Crate)](https://www.researchobject.org/ro-crate/).

Supports [RO-Crate 1.1](https://www.researchobject.org/ro-crate/specification/1.1/index.html) specification.

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

args = ['input.txt', 'output.txt']
ns = parser.parse_args(args)
# Tell recorder about input and output files
ios = IOs(input_files=["input"], output_files=["output"])
start_time = datetime.now()

# Do handling of the CLI command here...

# argv argument is optional, in real usage you can omit it
record_with_argparse(parser, ns, ios, start_time, argv=['example-cli'] + args)
```

<details>
<summary>
Will generate a `ro-crate-metadata.json` file in the current working directory describing the execution of the CLI command. (Click me to see crate content)
</summary>

```json
{
{
    "@context": "https://w3id.org/ro/crate/1.1/context",
    "@graph": [
        {
            "@id": "./",
            "@type": "Dataset",
            "datePublished": "2026-01-28T11:21:20.238826",
            "hasPart": [
                {
                    "@id": "data/input.txt"
                },
                {
                    "@id": "output.txt"
                }
            ]
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
            "@id": "myscript@1.0.0",
            "@type": "SoftwareApplication",
            "description": "Example CLI",
            "name": "myscript",
            "version": "1.0.0"
        },
        {
            "@id": "data/input.txt",
            "@type": "File",
            "contentSize": 446,
            "description": "Input file",
            "encodingFormat": "text/plain",
            "name": "data/input.txt"
        },
        {
            "@id": "output.txt",
            "@type": "File",
            "contentSize": 446,
            "description": "Output file",
            "encodingFormat": "text/plain",
            "name": "output.txt"
        },
        {
            "@id": "sverhoeven",
            "@type": "Person",
            "name": "sverhoeven"
        },
        {
            "@id": "./myscript.py data/input.txt output.txt",
            "@type": "CreateAction",
            "agent": {
                "@id": "sverhoeven"
            },
            "endTime": "2026-01-28T11:21:20.238826",
            "instrument": {
                "@id": "myscript@1.0.0"
            },
            "name": "./myscript.py data/input.txt output.txt",
            "object": [
                {
                    "@id": "data/input.txt"
                }
            ],
            "result": [
                {
                    "@id": "output.txt"
                }
            ],
            "startTime": "2026-01-28T11:21:20.238456"
        }
    ]
}
```

</details>

## Example

See the [example](example/) folder for a minimal example.

### Contributions

See [AGENTS.md](AGENTS.md) for commands and hints for contributions.
