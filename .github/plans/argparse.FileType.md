# Support FileType

When I create an argparser like

```python
parser = argparse.ArgumentParser()
parser.add_argument('--raw', type=argparse.FileType('wb', 0))
parser.add_argument('out', type=argparse.FileType('w', encoding='UTF-8'))
args = parser.parse_args(['--raw', 'raw.dat', 'file.txt'])
```

The record method should still work, by using args.raw.name and args.out.name to get the filenames.
When `-` is used for stdin/stdout, then no file should be recorded.
