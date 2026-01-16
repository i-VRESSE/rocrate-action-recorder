# Use directory as input/output

Currently it is expected that input and output paths point to files. However, in some cases it may be useful to specify a directory as input or output.

```python
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Process AlphaFold files and download corresponding PDBe mmCIF files"
)

parser.add_argument(
        "input_dir", type=Path, help="Directory with AlphaFold mmcif/PDB files"
    )
parser.add_argument(
        "output_dir", type=Path, help="Directory to store downloaded PDBe mmCIF files"
    )
```

See https://www.researchobject.org/ro-crate/specification/1.1/data-entities.html#directory-file-entity how to store directories in RO-Crate.
