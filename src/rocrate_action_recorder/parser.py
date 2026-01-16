"""Parser abstraction for supporting multiple CLI frameworks.

This module defines protocols for representing CLI parsers and arguments,
allowing the record() function to work with argparse, click, typer, and
other CLI frameworks without modification.
"""

import argparse
from pathlib import Path
from typing import Any, Protocol


class Argument(Protocol):
    """Protocol for CLI argument metadata."""

    @property
    def name(self) -> str:
        """The argument destination name (e.g., 'input', 'output')."""
        ...

    @property
    def help(self) -> str | None:
        """The help text for this argument."""
        ...


class Arguments(Protocol):
    """Protocol for accessing argument values from parsed arguments."""

    def get(self, name: str) -> Any:
        """Get the value of an argument by its destination name.

        Args:
            name: The argument destination name.

        Returns:
            The argument value, or None if not found.
        """
        ...


class Parser(Protocol):
    """Protocol for CLI parser metadata and argument introspection."""

    def get_program_name(self) -> str:
        """Get the name of the CLI program.

        Returns:
            The program name (e.g., 'myscript').
        """
        ...

    def get_description(self) -> str | None:
        """Get the description of the CLI program.

        Returns:
            The program description, or None if not set.
        """
        ...

    def find_argument(self, name: str) -> Argument | None:
        """Find argument metadata by destination name.

        Args:
            name: The argument destination name.

        Returns:
            The Argument metadata, or None if not found.
        """
        ...


class ArgparseArgument:
    """Adapter for argparse.Action to the Argument protocol."""

    def __init__(self, action: argparse.Action) -> None:
        """Initialize with an argparse action.

        Args:
            action: An argparse.Action instance.
        """
        self._action = action

    @property
    def name(self) -> str:
        """The argument destination name."""
        return self._action.dest

    @property
    def help(self) -> str | None:
        """The help text for this argument."""
        return self._action.help


class ArgparseArguments:
    """Adapter for argparse.Namespace to the Arguments protocol."""

    def __init__(self, namespace: argparse.Namespace) -> None:
        """Initialize with an argparse namespace.

        Args:
            namespace: An argparse.Namespace instance from parse_args().
        """
        self._namespace = namespace

    def get(self, name: str) -> Any:
        """Get the value of an argument by its destination name.

        Args:
            name: The argument destination name.

        Returns:
            The argument value, or None if not found.
        """
        return getattr(self._namespace, name, None)


class ArgparseRecorder:
    """Adapter for argparse.ArgumentParser to the Parser protocol."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """Initialize with an argparse parser.

        Args:
            parser: An argparse.ArgumentParser instance.
        """
        self._parser = parser

    def get_program_name(self) -> str:
        """Get the name of the CLI program."""
        return self._parser.prog

    def get_description(self) -> str | None:
        """Get the description of the CLI program."""
        return self._parser.description

    def find_argument(self, name: str) -> Argument | None:
        """Find argument metadata by destination name."""
        for action in self._parser._actions:
            if action.dest == name:
                return ArgparseArgument(action)
        return None


def _get_filename_from_arg(arg: Any) -> str | None:
    """Extract filename from an argument value.

    Handles string paths, Path objects, and file-like objects (e.g., from argparse.FileType).

    Args:
        arg: The argument value: string path, Path object, or file-like object.

    Returns:
        The filename as a string, or None if the argument represents stdin/stdout.

    Raises:
        ValueError: If the argument is not a valid type.
    """
    # Handle string paths
    if isinstance(arg, str):
        return arg

    # Handle Path objects
    if isinstance(arg, Path):
        return str(arg)

    # Handle file-like objects
    if hasattr(arg, "name"):
        filename = arg.name
        if isinstance(filename, str):
            # Skip stdin/stdout represented as '-' or '<stdin>'/'<stdout>'
            if filename in ("-", "<stdin>", "<stdout>"):
                return None
            # Skip if it looks like a file descriptor or object representation
            # e.g., '<_io.FileIO name=7 mode='rb+' closefd=True>'
            if filename.startswith("<") and filename.endswith(">"):
                return None
            return filename
        # If .name is an integer (file descriptor), it might be a closed file
        # or a special file like stdin/stdout. We can't reliably determine
        # what file it is, so skip it.
        if isinstance(filename, int):
            return None

    raise ValueError(
        f"Expected string path, Path object, or file-like object with .name attribute, "
        f"got {type(arg).__name__}"
    )
