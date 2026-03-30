"""Shared helpers for CLI framework adapters."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IOArgumentNames:
    """Which argument names have values that are input/output files or directories."""

    input_files: list[str] = field(default_factory=list[str])
    """List of argument names for input files."""
    output_files: list[str] = field(default_factory=list[str])
    """List of argument names for output files."""
    input_dirs: list[str] = field(default_factory=list[str])
    """List of argument names for input directories."""
    output_dirs: list[str] = field(default_factory=list[str])
    """List of argument names for output directories."""


def try_convert_to_path(item: Any) -> Path | None:
    """Try to convert a single item to a Path."""
    if hasattr(item, "name") and (
        item.name is None
        or item.name == "<stdin>"
        or item.name == "<stdout>"
        or item.name == "-"
    ):
        logger.warning(
            "Unable to convert stdin/stdout file-like object to Path, ignoring it"
        )
        return None

    if isinstance(item, Path):
        return item
    if hasattr(item, "name"):
        return Path(item.name)
    if item is None:
        logger.warning("Unable to convert None to Path, ignoring it")
        return None
    return Path(item)


def _flatten_nested_tuples(value: Any) -> list[Any]:
    """Flatten nested tuples recursively."""
    result: list[Any] = []
    if isinstance(value, tuple):
        for item in value:
            result.extend(_flatten_nested_tuples(item))
    else:
        result.append(value)
    return result


def value2paths(value: Any) -> list[Path]:
    """Convert a value to a list of deduplicated Path objects."""
    # Flatten nested tuples (e.g., from Cyclopts *args: ((Path1,), (Path2,)))
    if isinstance(value, tuple):
        value = _flatten_nested_tuples(value)

    paths: list[Path] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            path = try_convert_to_path(item)
            if path is not None:
                paths.append(path)
    else:
        path = try_convert_to_path(value)
        if path is not None:
            paths.append(path)

    seen: set[Path] = set()
    deduplicated: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduplicated.append(path)

    return deduplicated
