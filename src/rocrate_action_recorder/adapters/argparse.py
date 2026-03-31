"""Adapter for argparse CLI framework."""

import logging
from argparse import ArgumentParser, Namespace, _VersionAction
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

from rocrate_action_recorder.adapters.shared import (
    IOArgumentNames,
    value2paths,
)
from rocrate_action_recorder.adapters.shared import (
    try_convert_to_path as shared_try_convert_to_path,
)
from rocrate_action_recorder.core import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    record,
)

logger = logging.getLogger(__name__)


class MissingDestArgparseSubparserError(ValueError):
    """Raised when an argparse subparser is missing the 'dest' argument."""

    def __init__(self) -> None:
        super().__init__("Argparse subparsers must have a 'dest' parameter defined to identify the chosen subcommand")


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


def argparse_value2paths(v: Any) -> list[Path]:
    """Convert an argparse value to a list of Path objects.

    Handles single paths, file-like objects, and lists/tuples of paths.
    Deduplicates paths before returning.

    Args:
        v: The value from argparse arguments.

    Returns:
        A list of deduplicated Path objects. Empty list if value is not path-like.
    """
    return value2paths(v)


def try_convert_to_path(item: Any) -> Path | None:
    """Try to convert a single item to a Path."""
    return shared_try_convert_to_path(item)


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
            version = action.version.replace("%(prog)s", "").replace(parser.prog, "").strip()
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


def map_name2paths(parser: ArgumentParser, ns: Namespace, name: str) -> list[IOArgumentPath]:
    value = getattr(ns, name)
    help = argparse_help(parser, ns, name) or ""
    paths = argparse_value2paths(value)
    if not paths:
        logger.warning(f"Argument name '{name}' has no associated path-like argument value(s).")
    return [IOArgumentPath(name=name, path=path, help=help) for path in paths]


def map_names2paths(parser: ArgumentParser, ns: Namespace, names: list[str]) -> list[IOArgumentPath]:
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

    Hint:
        The argument names passed in :class:`IOArgumentNames` should be attributes on
        a :class:`argparse.Namespace` object returned by
        :meth:`parse_args() <argparse.ArgumentParser.parse_args>`.
        For example `parser.add_argument('--input-file')` would correspond to argument
        name `input_file`.

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


def record_argparse(
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

    Hint:
        The argument names passed in :class:`IOArgumentNames` should be attributes on a :class:`argparse.Namespace` object
        returned by :meth:`parse_args() <argparse.ArgumentParser.parse_args>`.
        For example `parser.add_argument('--input-file')`
        would correspond to argument name `input_file`.

    Warning:
        A RO-Crate can only be written to the directory that
        contains all the input/output files and directories.

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
    program, ioargs = collect_record_info_from_argparse(parser, ns, ios, software_version=software_version)
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


def recorded_argparse[T](
    parser: ArgumentParser | None = None,
    parser_argument: str | None = None,
    input_dirs: list[str] | None = None,
    output_dirs: list[str] | None = None,
    input_files: list[str] | None = None,
    output_files: list[str] | None = None,
    dataset_license: str | None = None,
    enabled_argument: str | None = None,
    crate_dir: Path | None = None,
    crate_dir_argument: str | None = None,
) -> Callable[[Callable[[Namespace], T]], Callable[[Namespace], T]]:
    """Decorator to record a CLI invocation in an RO-Crate using argparse.

    Hint:
        The argument names should be attributes on a :class:`argparse.Namespace` object
        returned by :meth:`parse_args() <argparse.ArgumentParser.parse_args>`.
        For example `parser.add_argument('--input-file')`
        would correspond to argument name `input_file`.

    Warning:
        A RO-Crate can only be written to the directory that
        contains all the input/output files and directories.

    Args:
        parser: The argument parser used to parse the command-line arguments.
            This is needed to extract program information and help texts for the arguments.
            Can not be used together with the `parser_argument` parameter.
        parser_argument: The name of the attribute in :class:`argparse.Namespace` object
            that contains the :class:`argparse.ArgumentParser` object.
            Can not be used together with the `parser` parameter.
        input_dirs: List of argument names representing input directories
        output_dirs: List of argument names representing output directories
        input_files: List of argument names representing input files
        output_files: List of argument names representing output files
        dataset_license: License string for the dataset.
            Use license identifiers from https://spdx.org/licenses/ if possible.
            If None, no license is recorded.
        enabled_argument: Name of the attribute in args that indicates whether
            to record the invocation. Records if None.
            If provided, the invocation is only recorded if `getattr(args, enabled_argument)` is truthy.
        crate_dir: Optional path to the RO-Crate directory.
            If None, uses current working directory.
            Can not be used together with the `crate_dir_argument` parameter.
        crate_dir_argument: Name of the attribute in args that specifies the RO-Crate directory.
            If None, uses the current working directory.
            Can not be used together with the `crate_dir` parameter.

    Returns:
        Decorator function

    Raises:
        ValueError:
            If the current user cannot be determined.
            If the specified paths are outside the crate root.
            If the software version cannot be determined based on the program name.
            If both crate_dir and crate_dir_argument are specified.
            If both parser and parser_argument are specified.
            If parser_argument is specified but does not point to an ArgumentParser instance.
        AttributeError:
            If parser_argument is specified but not found in args.
        MissingDestArgparseSubparserError:
            If parser has subparsers but dest is not set.
    """

    def decorator(func: Callable[[Namespace], T]) -> Callable[[Namespace], T]:
        @wraps(func)
        def wrapper(args: Namespace) -> T:
            start_datetime = datetime.now(tz=UTC)

            result = func(args)

            if enabled_argument is None or getattr(args, enabled_argument, False):
                if crate_dir and crate_dir_argument:
                    raise ValueError("Cannot specify both crate_dir and crate_dir_argument")
                my_crate_dir: Path | None = None
                if crate_dir is not None:
                    my_crate_dir = crate_dir
                if crate_dir_argument:
                    args_crate_dir = getattr(args, crate_dir_argument, None)
                    if args_crate_dir is not None:
                        my_crate_dir = Path(args_crate_dir)
                end_time = datetime.now(tz=UTC)
                ios = IOArgumentNames(
                    input_dirs=input_dirs or [],
                    output_dirs=output_dirs or [],
                    input_files=input_files or [],
                    output_files=output_files or [],
                )
                if parser is not None and parser_argument is not None:
                    raise ValueError("Cannot specify both parser and parser_argument")
                if parser is not None:
                    used_parser = parser
                elif parser_argument is not None:
                    used_parser = getattr(args, parser_argument)
                    if not isinstance(used_parser, ArgumentParser):
                        raise ValueError(
                            f"Argument '{parser_argument}' is not an ArgumentParser instance, it is a {type(used_parser)}"
                        )
                else:
                    raise ValueError("Must specify either parser or parser_argument")
                record_argparse(
                    parser=used_parser,
                    ns=args,
                    ios=ios,
                    start_time=start_datetime,
                    end_time=end_time,
                    crate_dir=my_crate_dir,
                    dataset_license=dataset_license,
                )

            return result

        return wrapper

    return decorator
