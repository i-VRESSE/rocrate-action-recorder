"""Adapter for Click CLI framework."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

import click

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


def click_help(ctx: click.Context, arg_name: str) -> str | None:
    """Get help text for a Click argument/option.

    Args:
        ctx: The Click context.
        arg_name: The normalized argument/option name.

    Returns:
        The help text if found, otherwise None.
    """
    for param in ctx.command.params:
        if param.name == arg_name and isinstance(param, click.Option):
            return param.help
    return None


def click_value2paths(value: Any) -> list[Path]:
    """Convert a Click parameter value to a list of Path objects.

    Handles single paths, file-like objects, and tuples/lists of paths.
    Deduplicates paths before returning.

    Args:
        value: A parsed Click parameter value.

    Returns:
        A list of deduplicated paths.
    """
    return value2paths(value)


def try_convert_to_path(item: Any) -> Path | None:
    """Try to convert a single item to a Path."""
    return shared_try_convert_to_path(item)


def program_from_context(ctx: click.Context) -> Program:
    """Extract Program information from a Click context.

    Args:
        ctx: The current Click context.

    Returns:
        Program with command and selected subcommand information.
    """
    context_chain: list[click.Context] = []
    current: click.Context | None = ctx
    while current is not None:
        context_chain.append(current)
        current = current.parent
    context_chain.reverse()

    root_ctx = context_chain[0]
    root_name = root_ctx.command.name or root_ctx.info_name or ""
    program = Program(
        name=root_name,
        description=root_ctx.command.help or "",
    )

    current_program = program
    for child_ctx in context_chain[1:]:
        subcommand_name = child_ctx.info_name or child_ctx.command.name or ""
        subprogram = Program(
            name=subcommand_name,
            description=child_ctx.command.help or "",
        )
        current_program.subcommands[subcommand_name] = subprogram
        current_program = subprogram

    return program


def map_name2paths(
    ctx: click.Context,
    params: dict[str, Any],
    name: str,
) -> list[IOArgumentPath]:
    """Map a single Click parameter name to IOArgumentPath entries."""
    if name not in params:
        logger.warning(f"Argument name '{name}' does not exist in parsed Click params.")
        return []

    value = params[name]
    help_text = click_help(ctx, name) or ""
    paths = click_value2paths(value)
    if not paths:
        logger.warning(f"Argument name '{name}' has no associated path-like argument value(s).")
    return [IOArgumentPath(name=name, path=path, help=help_text) for path in paths]


def map_names2paths(
    ctx: click.Context,
    params: dict[str, Any],
    names: list[str],
) -> list[IOArgumentPath]:
    """Map multiple Click parameter names to IOArgumentPath entries."""
    ioargs: list[IOArgumentPath] = []
    for name in names:
        ioargs.extend(map_name2paths(ctx, params, name))
    return ioargs


def collect_record_info_from_click(
    ctx: click.Context,
    params: dict[str, Any],
    ios: IOArgumentNames,
    software_version: str | None = None,
) -> tuple[Program, IOArgumentPaths]:
    """Collect Program and IOArgumentPaths from Click inputs.

    Args:
        ctx: Current Click context.
        params: Parsed Click parameters.
        ios: Parameter names that map to input/output files and directories.
        software_version: Optional program version override.

    Returns:
        A tuple of (Program, IOArgumentPaths).
    """
    program = program_from_context(ctx)
    if software_version is not None:
        program.version = software_version

    ioargs = IOArgumentPaths(
        input_files=map_names2paths(ctx, params, ios.input_files),
        output_files=map_names2paths(ctx, params, ios.output_files),
        input_dirs=map_names2paths(ctx, params, ios.input_dirs),
        output_dirs=map_names2paths(ctx, params, ios.output_dirs),
    )
    return program, ioargs


def record_click(
    ctx: click.Context,
    params: dict[str, Any],
    ios: IOArgumentNames,
    start_time: datetime,
    crate_dir: Path | None = None,
    argv: list[str] | None = None,
    end_time: datetime | None = None,
    current_user: str | None = None,
    software_version: str | None = None,
    dataset_license: str | None = None,
) -> Path:
    """Record a CLI invocation in an RO-Crate using Click.

    Hint:
        The argument names passed in :class:`IOArgumentNames` should match keys in
        `params` (typically `ctx.params`), which are the normalized Click parameter
        names. For example `@click.option('--input-file')` usually corresponds to
        parameter name `input_file`.

    Args:
        ctx: Current Click context.
        params: Parsed Click parameters.
        ios: Parameter names that map to input/output files and directories.
        start_time: Datetime when the action started.
        crate_dir: Optional path to RO-Crate directory.
        argv: Optional command arguments to use in action id.
        end_time: Optional datetime when action ended.
        current_user: Optional user override.
        software_version: Optional software version override.
        dataset_license: Optional dataset license string.

    Returns:
        Path to generated ro-crate-metadata.json.
    """
    program, ioargs = collect_record_info_from_click(
        ctx,
        params,
        ios,
        software_version=software_version,
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


def recorded_click[T](
    input_dirs: list[str] | None = None,
    output_dirs: list[str] | None = None,
    input_files: list[str] | None = None,
    output_files: list[str] | None = None,
    dataset_license: str | None = None,
    enabled_argument: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to record a CLI invocation in an RO-Crate using Click.

    Hint:
        The argument names for `input_dirs`, `output_dirs`, `input_files`, and
        `output_files` should match keys in `ctx.params` (normalized Click parameter
        names). For example `@click.option('--input-file')` usually corresponds to
        parameter name `input_file`.

    Args:
        input_dirs: Parameter names representing input directories.
        output_dirs: Parameter names representing output directories.
        input_files: Parameter names representing input files.
        output_files: Parameter names representing output files.
        dataset_license: License string for the dataset.
        enabled_argument: Optional parameter name controlling recording.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            start_datetime = datetime.now(tz=UTC)

            result = func(*args, **kwargs)

            ctx = click.get_current_context(silent=True)
            if ctx is None:
                logger.warning("No active Click context found, skipping RO-Crate recording.")
                return result

            params = ctx.params
            should_record = enabled_argument is None or bool(params.get(enabled_argument, False))
            if should_record:
                end_time = datetime.now(tz=UTC)
                ios = IOArgumentNames(
                    input_dirs=input_dirs or [],
                    output_dirs=output_dirs or [],
                    input_files=input_files or [],
                    output_files=output_files or [],
                )
                record_click(
                    ctx=ctx,
                    params=params,
                    ios=ios,
                    start_time=start_datetime,
                    end_time=end_time,
                    dataset_license=dataset_license,
                )

            return result

        return wrapper

    return decorator
