# AGENTS.md

```shell
uv sync                  # Install all dependencies
uv run pytest            # Run all tests
uvx ruff format          # Format code
uvx ruff check           # Check for issues
uv run pyright           # Type check code
uv build                 # Build package
uv run --group docs sphinx-build docs docs/_build  # Build documentation
```

## Style

- ruff
- use type hints everywhere
- Google style docstrings, in docstring to not repeat type as they are in function signature.
- test naming: `test_<function under test>_<given>`
- group tests on same function under `class Test_<function under test>:` with method `def test_<given>(self):`

## Important

- Don't manually activate venvs; `uv` handles this automatically
- `uvx` runs tools in isolated environments (no installation needed)
- Put imports at top of file not inside functions
- Prefer to start with empty function bodies then write tests and then write code (TDD)
- When function has more than 5 arguments, call it with named arguments for clarity
- When writing tests, prefer realistic data over mocks where possible