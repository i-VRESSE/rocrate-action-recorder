"""Adapter for argparse CLI framework."""

from argparse import _VersionAction, ArgumentParser, Namespace
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import logging

from rocrate_action_recorder.core import (
    IOArgumentPaths,
    IOArgumentPath,
    Program,
    record,
)

logger = logging.getLogger(__name__)


class MissingDestArgparseSubparserError(ValueError):
    """Raised when an argparse subparser is missing the 'dest' argument."""

    def __init__(self) -> None:
        super().__init__(
            "Argparse subparsers must have a 'dest' parameter defined to identify the chosen subcommand"
        )


def argparse_help(parser: ArgumentParser, ns: Namespace, arg_name: str) -> str | None:
    """Get help text for an argparse argument.

    Args:
        parser: The ArgumentParser instance.
        ns: The parsed Namespace from argparse.
        arg_name: The argument destination name.

    Returns:
        The help text if found, otherwise None.
    """
    for action in parser._actions:
        if action.dest == arg_name:
            return action.help

    # Find help in subparsers if applicable
    if hasattr(parser, "_subparsers") and parser._subparsers:
        for action in parser._subparsers._actions:
            if hasattr(action, "choices") and isinstance(action.choices, dict):
                dest = action.dest
                if not dest or dest == "==SUPPRESS==":
                    raise MissingDestArgparseSubparserError()
                subcommand_name = getattr(ns, dest, None)
                if subcommand_name and subcommand_name in action.choices:
                    subparser = action.choices[subcommand_name]
                    return argparse_help(subparser, ns, arg_name)


def try_convert_to_path(item: Any) -> Path | None:
    """Try to convert a single item to a Path."""
    if isinstance(item, Path):
        return item
    elif hasattr(item, "name"):
        if (
            item.name is None
            or item.name == "<stdin>"
            or item.name == "<stdout>"
            or item.name == "-"
        ):
            # TODO can not use argparse.FileType for input/output directories, that makes no sense
            logger.warning(
                "Unable to convert stdin/stdout file-like object to Path, ignoring it"
            )
            return None
        return Path(item.name)
    elif item is None:
        logger.warning("Unable to convert None to Path, ignoring it")
        return None
    return Path(item)


def argparse_value2paths(v: Any) -> list[Path]:
    """Convert an argparse value to a list of Path objects.

    Handles single paths, file-like objects, and lists/tuples of paths.
    Deduplicates paths before returning.

    Args:
        v: The value from argparse arguments.

    Returns:
        A list of deduplicated Path objects. Empty list if value is not path-like.
    """
    paths: list[Path] = []
    if isinstance(v, (list, tuple)):
        # Handle lists and tuples
        for item in v:
            path = try_convert_to_path(item)
            if path is not None:
                paths.append(path)
    else:
        # Handle single values
        path = try_convert_to_path(v)
        if path is not None:
            paths.append(path)

    # Deduplicate while preserving order (keep first occurrence)
    seen: set[Path] = set()
    deduplicated: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduplicated.append(path)

    return deduplicated


def version_from_parser(parser: ArgumentParser) -> str | None:
    """Attempt to extract version information from an ArgumentParser version action.

    Args:
        parser: The ArgumentParser instance.
    Returns:
        The version string if found, otherwise None.

    Example:

        >>> import argparse
        >>> from rocrate_action_recorder.adapters.argparse import version_from_parser
        >>>
        >>> parser = argparse.ArgumentParser(prog="example-cli")
        >>> _ = parser.add_argument('--version', action='version', version='1.2.3')
        >>>
        >>> version_from_parser(parser)
        '1.2.3'
    """
    for action in parser._actions:
        if isinstance(action, _VersionAction) and action.version is not None:
            version = (
                action.version.replace("%(prog)s", "").replace(parser.prog, "").strip()
            )
            return version
    return None


def program_from_parser(parser: ArgumentParser, ns: Namespace) -> Program:
    """Extract Program information from argparse parser and namespace.

    Args:
        parser: The ArgumentParser instance.
        ns: The parsed Namespace from argparse.
    Returns:
        A Program object with details about the CLI program.
    """
    program = Program(
        name=parser.prog,
        description=parser.description or "",
        version=version_from_parser(parser),
    )
    if hasattr(parser, "_subparsers") and parser._subparsers:
        for action in parser._subparsers._actions:
            if hasattr(action, "choices") and isinstance(action.choices, dict):
                dest = action.dest
                if not dest or dest == "==SUPPRESS==":
                    raise MissingDestArgparseSubparserError()
                subcommand_name = getattr(ns, dest, None)
                if subcommand_name and subcommand_name in action.choices:
                    subparser = action.choices[subcommand_name]
                    subprogram = program_from_parser(subparser, ns)
                    program.subcommands[subcommand_name] = subprogram
                break

    return program


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


def map_name2paths(
    parser: ArgumentParser, ns: Namespace, name: str
) -> list[IOArgumentPath]:
    value = getattr(ns, name)
    help = argparse_help(parser, ns, name) or ""
    paths = argparse_value2paths(value)
    if not paths:
        logger.warning(
            f"Argument name '{name}' has no associated path-like argument value(s)."
        )
    return [IOArgumentPath(name=name, path=path, help=help) for path in paths]


def map_names2paths(
    parser: ArgumentParser, ns: Namespace, names: list[str]
) -> list[IOArgumentPath]:
    args: list[IOArgumentPath] = []
    for name in names:
        paths = map_name2paths(parser, ns, name)
        args.extend(paths)
    return args


def collect_record_info_from_argparse(
    parser: ArgumentParser,
    ns: Namespace,
    ios: IOArgumentNames,
    software_version: str | None = None,
) -> tuple[Program, IOArgumentPaths]:
    """Collect Program and IOArgumentPaths from argparse so it can be recorded as an action in RO-Crate.

    Args:
        parser: The argparse.ArgumentParser used to parse the arguments.
        ns: The argparse.Namespace with parsed arguments.
        ios: The argument names that are inputs/outputs files/directories.
        software_version: Optional version string to override detected version.
    Returns:
        A tuple of (Program, IOArgumentPaths).
    """
    program = program_from_parser(parser, ns)
    if software_version is not None:
        program.version = software_version
    ioargs = IOArgumentPaths(
        input_files=map_names2paths(parser, ns, ios.input_files),
        output_files=map_names2paths(parser, ns, ios.output_files),
        input_dirs=map_names2paths(parser, ns, ios.input_dirs),
        output_dirs=map_names2paths(parser, ns, ios.output_dirs),
    )
    return program, ioargs


def record_with_argparse(
    parser: ArgumentParser,
    ns: Namespace,
    ios: IOArgumentNames,
    start_time: datetime,
    crate_dir: Path | None = None,
    argv: list[str] | None = None,
    end_time: datetime | None = None,
    current_user: str | None = None,
    software_version: str | None = None,
    dataset_license: str | None = None,
) -> Path:
    """Record a CLI invocation in an RO-Crate using argparse.

    Args:
        parser: The argparse.ArgumentParser used to parse the arguments.
        ns: The argparse.Namespace with parsed arguments.
        ios: The argument names that are inputs/outputs files/directories.
        start_time: The datetime when the action started.
        crate_dir: Optional path to the RO-Crate directory. If None, uses current working
            directory.
        argv: Optional list of command-line arguments. If None, uses sys.argv.
        end_time: Optional datetime when the action ended. If None, uses current time.
        current_user: Optional username of the user running the action. If None, attempts
            to determine it from the system.
        software_version: Optional version string of the software. If None, attempts to
            detect it automatically.
        dataset_license: Optional license string to set for the RO-Crate dataset.

    Returns:
        Path to the generated ro-crate-metadata.json file.

    Raises:
        ValueError:
            If the current user cannot be determined.
            If the specified paths are outside the crate root.
            If the software version cannot be determined based on the program name.
        MissingDestArgparseSubparserError:
            If parser has subparsers but dest is not set.
    """
    program, ioargs = collect_record_info_from_argparse(
        parser, ns, ios, software_version=software_version
    )
    return record(
        program=program,
        ioargs=ioargs,
        start_time=start_time,
        crate_dir=crate_dir,
        argv=argv,
        end_time=end_time,
        current_user=current_user,
        dataset_license=dataset_license,
    )
