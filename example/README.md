Calling the script with

```shell
./myscript.py --input data/input.txt --output results/output.txt
```

Would generate a [ro-crate-metadata.json](ro-crate-metadata.json) file.

# Validate

```shell
uvx --from roc-validator rocrate-validator validate -m -v --output-format json --output-file 
report.json
```