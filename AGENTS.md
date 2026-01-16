# AGENTS.md

```shell
uv sync                  # Install all dependencies
uv run pytest            # Run all tests
uvx ruff format          # Format code
uvx ruff check           # Check for issues
```

## Style

- ruff
- use type hints everywhere
- Google style docstrings, in docstring to not repeat type as they are in function signature.

## Important

- Don't manually activate venvs; `uv` handles this automatically
- `uvx` runs tools in isolated environments (no installation needed)
- Use `uv sync` at session start for reproducibility
- Put imports at top of file not inside functions
