"""Adapter for Cyclopts CLI framework."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, LiteralString
import logging
import inspect
import sys

from cyclopts import App

from rocrate_action_recorder.core import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    record,
)
from rocrate_action_recorder.adapters.shared import (
    IOArgumentNames,
    try_convert_to_path as shared_try_convert_to_path,
    value2paths,
)

logger = logging.getLogger(__name__)

INPUT_FILE: LiteralString = "INPUT_FILE"
"""Marker for Annotated argument that represent input file."""
INPUT_FILES: LiteralString = "INPUT_FILES"
"""Marker for Annotated argument that represent multiple input files."""
INPUT_DIR: LiteralString = "INPUT_DIR"
"""Marker for Annotated argument that represent input directory."""
INPUT_DIRS: LiteralString = "INPUT_DIRS"
"""Marker for Annotated argument that represent multiple input directories."""
OUTPUT_FILE: LiteralString = "OUTPUT_FILE"
"""Marker for Annotated argument that represent output file."""
OUTPUT_FILES: LiteralString = "OUTPUT_FILES"
"""Marker for Annotated argument that represent multiple output files."""
OUTPUT_DIR: LiteralString = "OUTPUT_DIR"
"""Marker for Annotated argument that represent output directory."""
OUTPUT_DIRS: LiteralString = "OUTPUT_DIRS"
"""Marker for Annotated argument that represent multiple output directories."""
RECORD_TRIGGER: LiteralString = "RECORD_TRIGGER"
"""Marker for Annotated boolean argument that trigger recording."""

_ORIGINAL_CYCLOPTS_APP_CALL = App.__call__


def cyclopts_help(
    app: App, bound_args: inspect.BoundArguments, arg_name: str
) -> str | None:
    """Get help text for a Cyclopts parameter.

    Args:
        app: The Cyclopts App instance.
        bound_args: The bound arguments from parsing.
        arg_name: The parameter name.

    Returns:
        The help text if found, otherwise None.
    """
    argument_collection = app.assemble_argument_collection()
    for arg in argument_collection:
        if hasattr(arg, "name") and arg.name == arg_name:
            if hasattr(arg, "field_info") and hasattr(arg.field_info, "annotation"):
                annotation = arg.field_info.annotation
                if hasattr(annotation, "__metadata__"):
                    metadata = annotation.__metadata__
                    if metadata:
                        return str(metadata[0])
    return None


def cyclopts_value2paths(value: Any) -> list[Path]:
    """Convert a Cyclopts parameter value to a list of Path objects.

    Handles single paths, file-like objects, and tuples/lists of paths.
    Deduplicates paths before returning.

    Args:
        value: A parsed Cyclopts parameter value.

    Returns:
        A list of deduplicated paths.
    """
    return value2paths(value)


def try_convert_to_path(item: Any) -> Path | None:
    """Try to convert a single item to a Path."""
    return shared_try_convert_to_path(item)


def program_from_app(
    app: App, bound_args: inspect.BoundArguments | None = None
) -> Program:
    """Extract Program information from a Cyclopts App.

    Args:
        app: The Cyclopts App instance.
        bound_args: Optional bound arguments for command-specific info.

    Returns:
        Program with command and selected subcommand information.
    """
    version = None
    if app.version:
        version_str = app.version() if callable(app.version) else app.version
        if version_str is not None:
            version = str(version_str)

    cmd = app.default_command
    description = ""
    if cmd:
        description = getattr(cmd, "__doc__", "") or ""

    program = Program(
        name=" ".join(app.name) if isinstance(app.name, tuple) else (app.name or ""),
        description=description,
        version=version,
    )

    subcommands_dict: dict[str, Program] = {}
    for sub_app in app.subapps:
        if sub_app.default_command:
            cmd = sub_app.default_command
            cmd_name = getattr(cmd, "__name__", "")
            subversion = None
            if sub_app.version:
                subversion_str = (
                    sub_app.version() if callable(sub_app.version) else sub_app.version
                )
                if subversion_str is not None:
                    subversion = str(subversion_str)
            subprogram = Program(
                name=cmd_name,
                description=getattr(cmd, "__doc__", "") or "",
                version=subversion,
            )
            subcommands_dict[cmd_name] = subprogram

    program.subcommands.update(subcommands_dict)

    return program


def make_parameter2field(app: App) -> dict[str, str]:
    param_to_field = {}
    argument_collection = app.assemble_argument_collection()
    for arg in argument_collection:
        param_name = arg.parameter.name
        if type(param_name) is tuple:
            param_name = param_name[0]
        field_name = arg.field_info.names[0]
        param_to_field[param_name] = field_name
    return param_to_field


def map_name2paths(
    app: App,
    bound_args: inspect.BoundArguments,
    name: str,
) -> list[IOArgumentPath]:
    """Map a single Cyclopts parameter name to IOArgumentPath entries."""
    parameter2field = make_parameter2field(app)
    field_name = parameter2field.get(name)

    if field_name not in bound_args.arguments:
        logger.warning(
            f"Argument name '{name}' does not exist in parsed Cyclopts args."
        )
        return []

    value = bound_args.arguments[field_name]
    help_text = cyclopts_help(app, bound_args, name) or ""
    paths = cyclopts_value2paths(value)
    if not paths:
        logger.warning(
            f"Argument name '{name}' has no associated path-like argument value(s)."
        )
    return [IOArgumentPath(name=name, path=path, help=help_text) for path in paths]


def map_names2paths(
    app: App,
    bound_args: inspect.BoundArguments,
    names: list[str],
) -> list[IOArgumentPath]:
    """Map multiple Cyclopts parameter names to IOArgumentPath entries."""
    ioargs: list[IOArgumentPath] = []
    for name in names:
        ioargs.extend(map_name2paths(app, bound_args, name))
    return ioargs


def collect_record_info_from_cyclopts(
    app: App,
    bound_args: inspect.BoundArguments,
    ios: IOArgumentNames,
    software_version: str | None = None,
) -> tuple[Program, IOArgumentPaths]:
    """Collect Program and IOArgumentPaths from Cyclopts inputs.

    Args:
        app: Current Cyclopts App instance.
        bound_args: Parsed Cyclopts bound arguments.
        ios: Parameter names that map to input/output files and directories.
        software_version: Optional program version override.

    Returns:
        A tuple of (Program, IOArgumentPaths).
    """
    program = program_from_app(app, bound_args)
    if software_version is not None:
        program.version = software_version

    ioargs = IOArgumentPaths(
        input_files=map_names2paths(app, bound_args, ios.input_files),
        output_files=map_names2paths(app, bound_args, ios.output_files),
        input_dirs=map_names2paths(app, bound_args, ios.input_dirs),
        output_dirs=map_names2paths(app, bound_args, ios.output_dirs),
    )
    return program, ioargs


def record_cyclopts(
    app: App,
    bound_args: inspect.BoundArguments,
    ios: IOArgumentNames,
    start_time: datetime,
    crate_dir: Path | None = None,
    argv: list[str] | None = None,
    end_time: datetime | None = None,
    current_user: str | None = None,
    software_version: str | None = None,
    dataset_license: str | None = None,
) -> Path:
    """Record a CLI invocation in an RO-Crate using Cyclopts.

    Hint:
        The argument names passed in :class:`IOArgumentNames` should match keys in
        the bound arguments (typically from `app.parse_args()` or the decorated function
        arguments). For example `def myfunc(input: Path, output: Path)` would correspond
        to parameter names `input` and `output`.

    Args:
        app: Current Cyclopts App instance.
        bound_args: Parsed Cyclopts bound arguments.
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
    program, ioargs = collect_record_info_from_cyclopts(
        app,
        bound_args,
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


def _detect_ios_from_app(app: App) -> IOArgumentNames:
    """Auto-detect input/output arguments from Annotated metadata.

    Args:
        app: The Cyclopts App instance.

    Returns:
        IOArgumentNames with detected argument names.

    Raises:
        ValueError: If no arguments with INPUT/OUTPUT markers are found.
    """
    ios = IOArgumentNames()

    for arg in app.assemble_argument_collection():
        name = arg.name.lstrip("-")
        ann = arg.field_info.annotation
        if hasattr(ann, "__metadata__"):
            for meta in ann.__metadata__:
                if meta is INPUT_FILE or meta is INPUT_FILES:
                    ios.input_files.append(name)
                elif meta is INPUT_DIR or meta is INPUT_DIRS:
                    ios.input_dirs.append(name)
                elif meta is OUTPUT_FILE or meta is OUTPUT_FILES:
                    ios.output_files.append(name)
                elif meta is OUTPUT_DIR or meta is OUTPUT_DIRS:
                    ios.output_dirs.append(name)

    if not any(vars(ios).values()):
        raise ValueError(
            "No arguments with INPUT_FILE/DIR/FILES/DIRS or OUTPUT_FILE/DIR/FILES/DIRS annotations found. "
            "Use Annotated[Path, INPUT_FILE] or similar markers on function parameters."
        )

    return ios


def _detect_record_trigger_from_app(app: App) -> str | None:
    """Detect the argument annotated as RECORD_TRIGGER.

    Args:
        app: The Cyclopts App instance.

    Returns:
        The trigger argument name if found, otherwise None.
    """
    for arg in app.assemble_argument_collection():
        name = arg.name.lstrip("-")
        ann = arg.field_info.annotation
        if hasattr(ann, "__metadata__"):
            for meta in ann.__metadata__:
                if meta == RECORD_TRIGGER:
                    return name
    return None


def _should_record(
    bound_args: inspect.BoundArguments,
    record_trigger_name: str | None,
) -> bool:
    """Evaluate whether recording should occur for this invocation.

    Args:
        bound_args: Parsed Cyclopts bound arguments.
        record_trigger_name: Optional trigger argument name.

    Returns:
        True when recording is enabled, otherwise False.
    """
    if record_trigger_name is None:
        return True

    trigger_value = bound_args.arguments.get(record_trigger_name)
    if trigger_value is None:
        return False

    return bool(trigger_value)


def run_with_record(
    app: App,
    crate_dir: Path | None = None,
    dataset_license: str | None = None,
    *args,
    **kwargs,
) -> None:
    """Record a CLI invocation in an RO-Crate using Cyclopts.

    Auto-detects input/output arguments from Annotated metadata on function parameters.
    Calls :meth:`cyclopts.App.__call__` internally to execute the CLI and record the invocation.

    Args:
        app: The Cyclopts App instance.
        crate_dir: Optional path to RO-Crate directory. If None, uses current directory.
        dataset_license: License string for the dataset.
        *args: Positional arguments passed to :meth:`cyclopts.App.__call__`.
        **kwargs: Keyword arguments passed to :meth:`cyclopts.App.__call__`.

    Raises:
        ValueError: If no arguments with INPUT/OUTPUT markers are found.
    """
    ios = _detect_ios_from_app(app)
    record_trigger_name = _detect_record_trigger_from_app(app)

    def patched_call(self: App, *args: Any, **kwargs: Any):
        start_time = datetime.now(tz=UTC)

        argv = args[0] if args else kwargs.get("tokens")
        if argv is None:
            argv = sys.argv[1:]
        elif isinstance(argv, str):
            argv = argv.split()
        elif hasattr(argv, "__iter__") and not isinstance(argv, list):
            argv = list(argv)

        cmd, bound_args, unused = self.parse_args(argv)

        try:
            result = _ORIGINAL_CYCLOPTS_APP_CALL(self, *args, **kwargs)
        except SystemExit as e:
            result = e.code

        end_time = datetime.now(tz=UTC)

        if _should_record(bound_args, record_trigger_name):
            record_cyclopts(
                app=self,
                bound_args=bound_args,
                ios=ios,
                start_time=start_time,
                end_time=end_time,
                crate_dir=crate_dir,
                argv=argv,
                dataset_license=dataset_license,
            )

        raise SystemExit(result)

    app.__class__.__call__ = patched_call

    try:
        app(*args, **kwargs)
    finally:
        app.__class__.__call__ = _ORIGINAL_CYCLOPTS_APP_CALL
