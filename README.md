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
parser.add_argument("--input", type=Path, required=True, help="Input file")
parser.add_argument("--output", type=Path, required=True, help="Output file")

args = ['--input', 'input.txt', '--output', 'output.txt']
ns = parser.parse_args(args)
ios = IOs(input_files=["input"], output_files=["output"])
start_time = datetime.now()

# Do handling of the CLI command here...

# named args are for portability, in real usage you can omit them
record_with_argparse(parser, ns, ios, start_time, software_version="1.2.3", argv=['example-cli'] + args)
```

<details>
<summary>
Will generate a `ro-crate-metadata.json` file in the current working directory describing the execution of the CLI command.
</summary>

```json
{
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-16T12:00:05+00:00",
                "hasPart": [{"@id": "input.txt"}, {"@id": "output.txt"}],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
            {
                "@id": "example-cli@1.2.3",
                "@type": "SoftwareApplication",
                "description": "Example CLI",
                "name": "example-cli",
                "version": "1.2.3",
            },
            {
                "@id": "input.txt",
                "@type": "File",
                "contentSize": 12,
                "description": "Input file",
                "encodingFormat": "text/plain",
                "name": "input.txt",
            },
            {
                "@id": "output.txt",
                "@type": "File",
                "contentSize": 12,
                "description": "Output file",
                "encodingFormat": "text/plain",
                "name": "output.txt",
            },
            {"@id": "test_user", "@type": "Person", "name": "test_user"},
            {
                "@id": "example-cli --input input.txt --output output.txt",
                "@type": "CreateAction",
                "agent": {"@id": "test_user"},
                "endTime": "2026-01-16T12:00:05+00:00",
                "instrument": {"@id": "example-cli@1.2.3"},
                "name": "example-cli --input input.txt --output output.txt",
                "object": [{"@id": "input.txt"}],
                "result": [{"@id": "output.txt"}],
                "startTime": "2026-01-16T12:00:00+00:00",
            },
        ],
    }
```

</details>

## Example

See the [example](example/) folder for a minimal example.

### Contributions

See [AGENTS.md](AGENTS.md) for commands and hints for contributions.
