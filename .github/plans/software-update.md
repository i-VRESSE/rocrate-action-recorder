# Sofware version updates

```shell
# myscript.py has version 1.0.0
example/myscript.py --input input.txt --output output.txt
# myscript.py gets version bumped to 2.0.0
example/myscript.py --input output2.txt --output output2.txt
```

When software version changes, add new SoftwareApplication to the RO-Crate.
Change SoftwareApplication.identifier to include version.
