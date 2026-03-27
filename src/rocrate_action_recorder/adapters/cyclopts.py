"""Adapter for Cyclopts CLI framework."""

from datetime import UTC, datetime
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any, LiteralString
import logging
import inspect
import sys

from cyclopts import App
from cyclopts.argument import ArgumentCollection

from rocrate_action_recorder.core import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    record,
)
from rocrate_action_recorder.adapters.shared import (
    IOArgumentNames,
    value2paths as cyclopts_value2paths,
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

_MARKER_TO_CATEGORY: dict[str, str] = {
    INPUT_FILE: "input_files",
    INPUT_FILES: "input_files",
    INPUT_DIR: "input_dirs",
    INPUT_DIRS: "input_dirs",
    OUTPUT_FILE: "output_files",
    OUTPUT_FILES: "output_files",
    OUTPUT_DIR: "output_dirs",
    OUTPUT_DIRS: "output_dirs",
}


def program_from_app(app: App) -> Program:
    """Extract Program information from a Cyclopts App.

    Args:
        app: The Cyclopts App instance.

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

    parent_name = (
        " ".join(app.name) if isinstance(app.name, tuple) else (app.name or "")
    )
    program = Program(
        name=parent_name,
        description=description,
        version=version,
    )

    subcommands_dict: dict[str, Program] = {}
    for sub_app in app.subapps:
        if sub_app.default_command and inspect.isfunction(sub_app.default_command):
            cmd = sub_app.default_command
            cmd_name = getattr(cmd, "__name__", "")
            subversion = None
            if sub_app.version:
                subversion_str = (
                    sub_app.version() if callable(sub_app.version) else sub_app.version
                )
                if subversion_str is not None:
                    subversion = str(subversion_str)
            full_name = f"{parent_name} {cmd_name}".strip() if parent_name else cmd_name
            subprogram = Program(
                name=full_name,
                description=getattr(cmd, "__doc__", "") or "",
                version=subversion,
            )
            subcommands_dict[cmd_name] = subprogram

    program.subcommands.update(subcommands_dict)

    return program


def _lookup_argument_value(arguments: dict[str, Any], field_name: str) -> Any | None:
    """Resolve an argument value from Cyclopts bound arguments.

    Cyclopts stores grouped parameters, such as dataclass-backed option groups,
    under their parent parameter name in ``bound_args.arguments``. This helper
    resolves both top-level and nested field values.

    Args:
        arguments: Parsed Cyclopts bound arguments.
        field_name: Field name to resolve.

    Returns:
        The resolved value, or None if the field cannot be found.
    """
    if field_name in arguments:
        return arguments[field_name]

    def search(value: Any) -> Any | None:
        if value is None:
            return None

        if isinstance(value, dict):
            if field_name in value:
                return value[field_name]
            for nested_value in value.values():
                resolved = search(nested_value)
                if resolved is not None:
                    return resolved
            return None

        if is_dataclass(value):
            if hasattr(value, field_name):
                return getattr(value, field_name)
            for nested_name in value.__dataclass_fields__:
                resolved = search(getattr(value, nested_name))
                if resolved is not None:
                    return resolved
            return None

        if hasattr(value, field_name):
            return getattr(value, field_name)

        return None

    for argument_value in arguments.values():
        resolved = search(argument_value)
        if resolved is not None:
            return resolved

    return None


def collect_record_info_from_cyclopts(
    app: App,
    bound_args: inspect.BoundArguments,
    ios: IOArgumentNames,
    argument_collection: ArgumentCollection,
    software_version: str | None = None,
    executed_app: App | None = None,
) -> tuple[Program, IOArgumentPaths]:
    """Collect Program and IOArgumentPaths from Cyclopts inputs.

    Args:
        app: Root Cyclopts App instance.
        bound_args: Parsed Cyclopts bound arguments.
        ios: Parameter names that map to input/output files and directories.
        argument_collection: Assembled Cyclopts argument collection (from the executed subapp).
        software_version: Optional program version override.
        executed_app: Leaf App that was actually invoked; if provided, it is used for future
            program-name construction in nested subcommand scenarios.

    Returns:
        A tuple of (Program, IOArgumentPaths).
    """
    program = program_from_app(app)
    if software_version is not None:
        program.version = software_version

    name_info: dict[str, tuple[str, str]] = {}
    for arg in argument_collection:
        name = arg.name.lstrip("-")
        field_name = arg.field_info.names[0]
        ann = arg.field_info.annotation
        help_text = (
            str(ann.__metadata__[0])
            if hasattr(ann, "__metadata__") and ann.__metadata__
            else ""
        )
        name_info[name] = (field_name, help_text)

    def resolve(names: list[str]) -> list[IOArgumentPath]:
        result: list[IOArgumentPath] = []
        for name in names:
            info = name_info.get(name)
            if info is None:
                logger.warning(
                    f"Argument name '{name}' does not exist in parsed Cyclopts args."
                )
                continue
            field_name, help_text = info
            value = _lookup_argument_value(bound_args.arguments, field_name)
            if value is None:
                logger.warning(
                    f"Argument name '{name}' does not exist in parsed Cyclopts args."
                )
                continue
            paths = cyclopts_value2paths(value)
            if not paths:
                logger.warning(
                    f"Argument name '{name}' has no associated path-like argument value(s)."
                )
            result.extend(
                IOArgumentPath(name=name, path=p, help=help_text) for p in paths
            )
        return result

    ioargs = IOArgumentPaths(
        input_files=resolve(ios.input_files),
        output_files=resolve(ios.output_files),
        input_dirs=resolve(ios.input_dirs),
        output_dirs=resolve(ios.output_dirs),
    )
    return program, ioargs


def record_cyclopts(
    app: App,
    bound_args: inspect.BoundArguments,
    ios: IOArgumentNames,
    argument_collection: ArgumentCollection,
    start_time: datetime,
    crate_dir: Path | None = None,
    argv: list[str] | None = None,
    end_time: datetime | None = None,
    current_user: str | None = None,
    software_version: str | None = None,
    dataset_license: str | None = None,
    executed_app: App | None = None,
) -> Path:
    """Record a CLI invocation in an RO-Crate using Cyclopts.

    Hint:
        The argument names passed in :class:`IOArgumentNames` should match keys in
        the bound arguments (typically from `app.parse_args()` or the decorated function
        arguments). For example `def myfunc(input: Path, output: Path)` would correspond
        to parameter names `input` and `output`.

    Args:
        app: Root Cyclopts App instance.
        bound_args: Parsed Cyclopts bound arguments.
        ios: Parameter names that map to input/output files and directories.
        argument_collection: Assembled Cyclopts argument collection (from the executed subapp).
        start_time: Datetime when the action started.
        crate_dir: Optional path to RO-Crate directory.
        argv: Optional command arguments to use in action id.
        end_time: Optional datetime when action ended.
        current_user: Optional user override.
        software_version: Optional software version override.
        dataset_license: Optional dataset license string.
        executed_app: Leaf App that was actually invoked.

    Returns:
        Path to generated ro-crate-metadata.json.
    """
    program, ioargs = collect_record_info_from_cyclopts(
        app,
        bound_args,
        ios,
        argument_collection,
        software_version=software_version,
        executed_app=executed_app,
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


def _detect_ios_and_trigger(
    argument_collection: ArgumentCollection,
) -> tuple[IOArgumentNames, str | None]:
    """Auto-detect input/output arguments and optional record trigger from Annotated metadata.

    Args:
        argument_collection: Assembled Cyclopts argument collection.

    Returns:
        A tuple of (IOArgumentNames, trigger_arg_name_or_None).

    Raises:
        ValueError: If no arguments with INPUT/OUTPUT markers are found.
    """
    ios = IOArgumentNames()
    record_trigger_name: str | None = None

    for arg in argument_collection:
        name = arg.name.lstrip("-")
        ann = arg.field_info.annotation
        if not hasattr(ann, "__metadata__"):
            continue
        for meta in ann.__metadata__:
            if meta in _MARKER_TO_CATEGORY:
                getattr(ios, _MARKER_TO_CATEGORY[meta]).append(name)
            elif meta == RECORD_TRIGGER:
                record_trigger_name = name

    if not any(vars(ios).values()):
        raise ValueError(
            "No arguments with INPUT_FILE/DIR/FILES/DIRS or OUTPUT_FILE/DIR/FILES/DIRS annotations found. "
            "Use Annotated[Path, INPUT_FILE] or similar markers on function parameters."
        )

    return ios, record_trigger_name


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

    trigger_value = _lookup_argument_value(bound_args.arguments, record_trigger_name)
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
        ValueError: If no arguments with INPUT/OUTPUT markers are found on the executed command.
    """

    def patched_call(self: App, *args: Any, **kwargs: Any):
        start_time = datetime.now(tz=UTC)

        argv = args[0] if args else kwargs.get("tokens")
        if argv is None:
            argv = sys.argv[1:]
        elif isinstance(argv, str):
            argv = argv.split()
        elif hasattr(argv, "__iter__") and not isinstance(argv, list):
            argv = list(argv)

        command, bound_args, _ = self.parse_args(argv)
        executed_app = next(
            (sub for sub in self.subapps if sub.default_command is command),
            self,
        )
        argument_collection = executed_app.assemble_argument_collection()
        ios, record_trigger_name = _detect_ios_and_trigger(argument_collection)

        try:
            result = _ORIGINAL_CYCLOPTS_APP_CALL(self, *args, **kwargs)
        except SystemExit as e:
            result = e.code

        end_time = datetime.now(tz=UTC)

        if _should_record(bound_args, record_trigger_name):
            record_cyclopts(
                app=self,
                executed_app=executed_app,
                bound_args=bound_args,
                ios=ios,
                argument_collection=argument_collection,
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
