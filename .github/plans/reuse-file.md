# Reuse file

```shell
example/myscript.py --input input.txt --output output.txt
example/myscript.py --input output.txt --output output2.txt
```

When file (output.txt) is already mentioned in ro-crate-metadata.json then do not add it twice.
Do update date and size.
Add test in tests/test_record.py to verify that the reused file is correctly linked in the RO-Crate.

