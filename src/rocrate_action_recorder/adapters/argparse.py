"""Adapter for argparse CLI framework."""

from argparse import _VersionAction, ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from typing import Any

from rocrate_action_recorder.core import (
    IOArgument,
    Info,
    IOs,
    Program,
    record,
)


def argparse_help(parser: ArgumentParser, arg_name: str) -> str | None:
    """Get help text for an argparse argument.

    Args:
        parser: The ArgumentParser instance.
        arg_name: The argument destination name.

    Returns:
        The help text if found, otherwise None.
    """
    for action in parser._actions:
        if action.dest == arg_name:
            return action.help
    return None


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
                return None
            return Path(item.name)
        elif isinstance(item, str):
            return Path(item)
        return None

    # Handle lists and tuples
    if isinstance(v, (list, tuple)):
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
        >>> parser = argparse.ArgumentParser(prog="example-cli")
        >>> parser.add_argument('--version', action='version', version='1.2.3')
        >>> version_from_parser(parser)
        '1.2.3'
    """
    for action in parser._actions:
        if isinstance(action, _VersionAction) and action.version is not None:
            return (
                action.version.replace("%(prog)s", "").replace(parser.prog, "").strip()
            )
    return None


def argparse_info(args: Namespace, parser: ArgumentParser) -> Info:
    """Extract program and IO information from argparse results.

    Args:
        args: The parsed Namespace from argparse.
        parser: The ArgumentParser instance.

    Returns:
        An Info object with program details and IO arguments.

    Raises:
        ValueError: If parser has subparsers but dest is not set.
    """
    ioarguments: dict[str, list[IOArgument]] = {}
    for k, v in args._get_kwargs():
        paths = argparse_value2paths(v)
        if not paths:  # Skip empty lists
            continue
        # Skip if key already exists
        if k in ioarguments:
            continue
        help = argparse_help(parser, k) or ""
        ioarguments[k] = [IOArgument(name=k, path=path, help=help) for path in paths]

    program = Program(
        name=parser.prog,
        description=parser.description or "",
    )

    # Handle subcommands if present
    if hasattr(parser, "_subparsers") and parser._subparsers:
        for action in parser._subparsers._actions:
            if hasattr(action, "choices") and isinstance(action.choices, dict):
                dest = action.dest
                if not dest or dest == "==SUPPRESS==":
                    raise ValueError(
                        "record_with_argparse requires add_subparsers(dest='name') "
                        "with dest parameter set"
                    )

                subcommand_name = getattr(args, dest, None)
                if subcommand_name and subcommand_name in action.choices:
                    subparser = action.choices[subcommand_name]
                    subinfo = argparse_info(args, subparser)
                    program.subcommands[subcommand_name] = subinfo.program
                    # Merge ioarguments from subcommand
                    ioarguments.update(subinfo.ioarguments)
                break

    return Info(
        program=program,
        ioarguments=ioarguments,
    )


def record_with_argparse(
    parser: ArgumentParser,
    ns: Namespace,
    ios: IOs,
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
        ios: The IOs specifying which arguments are inputs and outputs.
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

    Example:
        >>> import argparse
        >>> from datetime import datetime
        >>> from pathlib import Path
        >>> from rocrate_action_recorder import record_with_argparse, IOs
        >>>
        >>> parser = argparse.ArgumentParser(prog="example-cli", description="Example CLI")
        >>> parser.add_argument("--input", type=Path, required=True, help="Input file")
        >>> parser.add_argument("--output", type=Path, required=True, help="Output file")
        >>> args = ['--input', 'data/input.txt', '--output', 'data/output.txt']
        >>> ns = parser.parse_args(args)
        >>> ios = IOs(input_files=["input"], output_files=["output"])
        >>> start_time = datetime.now()
        >>> # named args are for portability, in real usage you can omit them
        >>> record_with_argparse(parser, ns, ios, start_time, software_version="1.2.3", argv=['example-cli'] + args)
        Path('ro-crate-metadata.json')
    """
    info = argparse_info(ns, parser)
    if software_version is None:
        software_version = version_from_parser(parser)
    return record(
        info=info,
        ios=ios,
        start_time=start_time,
        crate_dir=crate_dir,
        argv=argv,
        end_time=end_time,
        current_user=current_user,
        software_version=software_version,
        dataset_license=dataset_license,
    )
