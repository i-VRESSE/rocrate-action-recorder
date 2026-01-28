Calling the script with

```shell
./myscript.py data/input.txt output.txt
```

Would generate a [ro-crate-metadata.json](ro-crate-metadata.json) file.

# Validate the RO-Crate

```shell
uvx --from roc-validator rocrate-validator validate -v --output-format json --output-file report.json
```

Should output something like
```shell

  🔍 Validating RO-Crate against profile: process-run-crate-0.5......... DONE!

  ✅ Validation PASSED!. 
     RO-Crate is valid according to the profile(s): process-run-crate-0.5

  📝 Writing validation results in JSON format to the file "report.json".... DONE!
```