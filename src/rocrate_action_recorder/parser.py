"""Parser abstraction for supporting multiple CLI frameworks.

This module defines protocols for representing CLI parsers and arguments,
allowing the record() function to work with argparse, click, typer, and
other CLI frameworks without modification.
"""

import argparse
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
