# rocrate-action-recorder

Records calls of cli commands into a [Research Object Crate (RO-Crate)](https://www.researchobject.org/ro-crate/).

Supports [RO-Crate 1.1](https://www.researchobject.org/ro-crate/specification/1.1/index.html) specification..

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

args = ['--input', 'data/input.txt', '--output', 'data/output.txt']
ns = parser.parse_args(args)
ios = IOs(input_files=["input"], output_files=["output"])
start_time = datetime.now()

# Do handling of the CLI command here...

# named args are for portability, in real usage you can omit them
record_with_argparse(parser, ns, ios, start_time, software_version="1.2.3", argv=['example-cli'] + args)
```

Will generate a `ro-crate-metadata.json` file in the current working directory describing the execution of the CLI command.

## Example

See the [example](example/) folder for a minimal example.

### Contributions

See [AGENTS.md](AGENTS.md) for commands and hints for contributions.
