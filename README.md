# rocrate-action-recorder

Records calls of cli commands into a Research Object Crate (RO-Crate).

## Install

```shell
pip install rocrate-action-recorder
```

## Usage

```python
import argparse
import datetime.datetime
from pathlib import Path
from rocrate_action_recorder import record

parser = argparse.ArgumentParser(prog="example-cli", description="Example CLI")
parser.add_argument("--input", type=Path, required=True, help="Input file")
parser.add_argument("--output", type=Path, required=True, help="Output file")
args = parser.parse_args(['--input', 'data/input.txt', '--output', 'data/output.txt'])

record(
    args=args,
    parser=parser,
    argv=['example-cli', '--input', 'data/input.txt', '--output', 'data/output.txt'],
    inputs=['input'],
    outputs=['output'],
    start_time=datetime.datetime.now(),
)
```

Will generate a `ro-crate-metadata.json` file in the current working directory describing the execution of the CLI command.

## Example

See the [example](example/) folder for a minimal example.

