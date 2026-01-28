Calling the script with

```shell
./myscript.py data/input.txt output.txt
```

Would generate a [ro-crate-metadata.json](ro-crate-metadata.json) file.

# Validate the RO-Crate

```shell
uvx --from roc-validator rocrate-validator validate -v --output-format json --output-file report.json
```