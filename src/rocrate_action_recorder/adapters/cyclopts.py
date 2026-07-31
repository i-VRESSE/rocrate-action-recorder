"""Adapter for Cyclopts CLI framework."""

import inspect
import logging
import shlex
import sys
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, LiteralString, get_args, get_origin

from cyclopts import App
from cyclopts.argument import ArgumentCollection
from cyclopts.help import format_doc
from cyclopts.help.inline_text import InlineText

from rocrate_action_recorder.adapters.shared import (
    IOArgumentNames,
    try_convert_to_path,
    value2paths,
)
from rocrate_action_recorder.core import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    record,
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
CRATE_DIR: LiteralString = "CRATE_DIR"
"""Marker for Annotated Path argument that specifies the RO-Crate directory."""

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


def _annotation_markers(annotation: Any, extra_metadata: Iterable[Any] = ()) -> list[Any]:
    """Collect Annotated-style metadata from an annotation tree.

    This unwraps nested ``Annotated`` values that may be wrapped inside
    ``Optional``/union annotations.
    """
    markers = list(extra_metadata)
    origin = get_origin(annotation)

    if origin is Annotated:
        annotated_args = get_args(annotation)
        if annotated_args:
            base_annotation, *metadata = annotated_args
            markers.extend(metadata)
            return _annotation_markers(base_annotation, markers)

    if origin is not None:
        for arg in get_args(annotation):
            markers.extend(_annotation_markers(arg))
        return markers

    if hasattr(annotation, "__metadata__"):
        markers.extend(annotation.__metadata__)

    return markers


def _collect_subcommands(app: App, parent_name: str, seen: set[str] | None = None) -> dict[str, Program]:
    """Recursively collect all subcommands from a Cyclopts App.

    Args:
        app: The Cyclopts App instance to collect from.
        parent_name: The accumulated name path of parent commands.
        seen: Set of app name strings to track visited apps and avoid infinite recursion.

    Returns:
        Dictionary mapping command names to Program objects.
    """
    subcommands_dict: dict[str, Program] = {}

    for sub_app in app.subapps:
        # Skip built-in subapps
        if sub_app.name in (
            ("help-print",),
            ("version-print",),
            ("install-completion-command",),
        ):
            continue

        sub_app_name = " ".join(sub_app.name) if isinstance(sub_app.name, tuple) else (sub_app.name or "")
        cmd_name = sub_app_name

        # Check if this sub_app has a default command that is a function
        if sub_app.default_command and inspect.isfunction(sub_app.default_command):
            subversion = None
            if sub_app.version:
                subversion_str = sub_app.version() if callable(sub_app.version) else sub_app.version
                if subversion_str is not None:
                    subversion = str(subversion_str)
            full_name = f"{parent_name} {cmd_name}".strip() if parent_name else cmd_name
            subprogram = Program(
                name=full_name,
                description=_plaintext_doc(sub_app),
                version=subversion,
            )
            subcommands_dict[cmd_name] = subprogram

        # Recursively collect commands from this sub_app's children
        nested_subcommands = _collect_subcommands(
            sub_app,
            f"{parent_name} {cmd_name}".strip() if parent_name else cmd_name,
            seen,
        )
        for nested_name, nested_program in nested_subcommands.items():
            # Only add if not already present (parent commands take precedence)
            if nested_name not in subcommands_dict:
                subcommands_dict[nested_name] = nested_program

    return subcommands_dict


def _plaintext_doc(app: App) -> str:
    """Extract plaintext description from a Cyclopts App's docstring."""
    doc = format_doc(app, "plaintext")
    if isinstance(doc, InlineText):
        # primary_renderable has rich.text.Text type, force to string
        return str(doc.primary_renderable)
    return ""


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

    description = _plaintext_doc(app)

    parent_name = " ".join(app.name) if isinstance(app.name, tuple) else (app.name or "")
    program = Program(
        name=parent_name,
        description=description,
        version=version,
    )

    # Recursively collect all subcommands
    subcommands_dict = _collect_subcommands(app, parent_name)
    program.subcommands.update(subcommands_dict)

    return program


def _is_pydantic_model(value: Any) -> bool:
    """Check if a value is a Pydantic BaseModel instance."""
    try:
        from pydantic import BaseModel

        return isinstance(value, BaseModel)
    except ImportError:
        return False


def _is_attrs_instance(value: Any) -> bool:
    """Check if a value is an attrs instance."""
    try:
        import attrs

        return attrs.has(type(value))
    except ImportError:
        return False


def _search_argument_value(value: Any, field_name: str) -> Any | None:
    """Search recursively for a field value within parsed Cyclopts arguments.

    Args:
        value: Value to inspect.
        field_name: Field name to resolve.

    Returns:
        The resolved value, or None if the field cannot be found.
    """
    if value is None:
        return None

    if is_dataclass(value):
        if hasattr(value, field_name):
            return getattr(value, field_name)
        for nested_name in value.__dataclass_fields__:
            resolved = _search_argument_value(getattr(value, nested_name), field_name)
            if resolved is not None:
                return resolved
        return None

    if _is_pydantic_model(value):
        if hasattr(value, field_name):
            return getattr(value, field_name)
        # Pydantic models have __fields__ (Pydantic v1) or model_fields (Pydantic v2)
        # Access from class to avoid deprecation warning in Pydantic v2.11+
        model_cls = type(value)
        fields = getattr(model_cls, "model_fields", None) or getattr(model_cls, "__fields__", None)
        if fields:
            for nested_name in fields:
                resolved = _search_argument_value(getattr(value, nested_name), field_name)
                if resolved is not None:
                    return resolved
        return None

    if _is_attrs_instance(value):
        if hasattr(value, field_name):
            return getattr(value, field_name)
        attrs_attrs = getattr(type(value), "__attrs_attrs__", None)
        if attrs_attrs:
            for attr in attrs_attrs:
                nested_name = attr.name
                resolved = _search_argument_value(getattr(value, nested_name), field_name)
                if resolved is not None:
                    return resolved
        return None

    if isinstance(value, tuple):
        for item in value:
            resolved = _search_argument_value(item, field_name)
            if resolved is not None:
                return resolved
        return None

    if hasattr(value, field_name):
        return getattr(value, field_name)

    return None


def _lookup_argument_value(arguments: dict[str, Any], field_name: str) -> Any | None:
    """Resolve an argument value from Cyclopts bound arguments.

    Cyclopts stores grouped parameters, such as dataclass-backed option groups,
    under their parent parameter name in ``bound_args.arguments``. This helper
    resolves both top-level and nested field values.

    Args:
        arguments: Parsed Cyclopts bound arguments.
        field_name: Field name to resolve. Supports dot notation for nested fields.

    Returns:
        The resolved value, or None if the field cannot be found.
    """
    # Handle dot notation for nested field paths (e.g., "config.prov")
    if "." in field_name:
        parts = field_name.split(".", 1)
        top_level = arguments.get(parts[0])
        if top_level is not None:
            return _lookup_nested_field(top_level, parts[1])
        return None

    if field_name in arguments:
        return arguments[field_name]

    for argument_value in arguments.values():
        resolved = _search_argument_value(argument_value, field_name)
        if resolved is not None:
            return resolved

    return None


def _lookup_nested_field(value: Any, field_path: str) -> Any | None:
    """Lookup a nested field value using dot notation.

    Args:
        value: The value to search in (Pydantic model, dataclass, attrs, dict, etc.).
        field_path: Dot-separated field path (e.g., "io.input").

    Returns:
        The resolved value, or None if the field cannot be found.
    """
    parts = field_path.split(".", 1)
    current_field = parts[0]

    if value is None:
        return None

    if hasattr(value, current_field):
        if hasattr(value, current_field):
            current_value = getattr(value, current_field)
        else:
            return None
    else:
        return None

    # If there are more parts, recurse
    if len(parts) > 1:
        return _lookup_nested_field(current_value, parts[1])

    return current_value


def _resolve_crate_dir_value(value: Any, field_name: str) -> Path | None:
    """Resolve a CRATE_DIR-marked value to a concrete path.

    Args:
        value: Parsed argument value.
        field_name: Argument name used for developer-facing errors.

    Returns:
        A resolved crate directory path, or None when the value is intentionally unset.

    Raises:
        ValueError: If the CRATE_DIR marker is applied to a non-path-like value.
    """
    if value is None:
        return None

    path = try_convert_to_path(value)
    if path is not None:
        return path

    value_type = type(value).__name__
    raise ValueError(
        f"Argument '{field_name}' is annotated with CRATE_DIR but resolved to {value_type}, which is not path-like. "
        "CRATE_DIR must annotate a pathlib.Path, str, os.PathLike, or equivalent path-convertible value. "
        f"Fix the CLI by changing '{field_name}' to a path-like type."
    )


def _resolve_io_argument_paths(
    names: list[str],
    name_info: dict[str, tuple[str, str]],
    arguments: dict[str, Any],
) -> list[IOArgumentPath]:
    """Resolve named Cyclopts arguments to path-bearing IOArgumentPath entries.

    Args:
        names: IO argument names to resolve.
        name_info: Mapping from CLI argument name to bound field name and help text.
        arguments: Parsed Cyclopts bound arguments.

    Returns:
        Resolved IO argument path entries.
    """
    result: list[IOArgumentPath] = []
    for name in names:
        info = name_info.get(name)
        if info is None:
            logger.warning(f"Argument name '{name}' does not exist in parsed Cyclopts args.")
            continue
        field_name, help_text = info
        value = _lookup_argument_value(arguments, field_name)
        if value is None:
            logger.warning(f"Argument name '{name}' does not exist in parsed Cyclopts args.")
            continue
        paths = value2paths(value)
        if not paths:
            logger.warning(f"Argument name '{name}' has no associated path-like argument value(s).")
        result.extend(IOArgumentPath(name=name, path=path, help=help_text) for path in paths)
    return result


def _collect_ioargs(
    bound_args: inspect.BoundArguments,
    ios: IOArgumentNames,
    argument_collection: ArgumentCollection,
) -> IOArgumentPaths:
    """Collect IOArgumentPaths from Cyclopts inputs.

    Args:
        bound_args: Parsed Cyclopts bound arguments.
        ios: Parameter names that map to input/output files and directories.
        argument_collection: Assembled Cyclopts argument collection (from the executed subapp).

    Returns:
        A IOArgumentPaths instance
    """
    name_info: dict[str, tuple[str, str]] = {}
    for arg in argument_collection:
        name = arg.name.lstrip("-")
        field_name = arg.field_info.names[0]
        help_text = ""
        if arg.parameter.help:
            help_text = arg.parameter.help
        name_info[name] = (field_name, help_text)

    ioargs = IOArgumentPaths(
        input_files=_resolve_io_argument_paths(ios.input_files, name_info, bound_args.arguments),
        output_files=_resolve_io_argument_paths(ios.output_files, name_info, bound_args.arguments),
        input_dirs=_resolve_io_argument_paths(ios.input_dirs, name_info, bound_args.arguments),
        output_dirs=_resolve_io_argument_paths(ios.output_dirs, name_info, bound_args.arguments),
    )
    return ioargs


def _extract_markers_from_pydantic_fields(model_cls: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Extract markers from Pydantic model fields.

    Args:
        model_cls: Pydantic model class.
        prefix: Field name prefix for nested fields.

    Returns:
        List of (field_path, marker) tuples.
    """
    markers: list[tuple[str, str]] = []
    fields = getattr(model_cls, "model_fields", None) or getattr(model_cls, "__fields__", None)
    if not fields:
        return markers

    for field_name, field_info in fields.items():
        field_path = f"{prefix}.{field_name}" if prefix else field_name
        ann = field_info.annotation
        metadata = getattr(field_info, "metadata", ())

        for meta in _annotation_markers(ann, metadata):
            if meta in _MARKER_TO_CATEGORY or meta in (RECORD_TRIGGER, CRATE_DIR):
                markers.append((field_path, meta))

        # Recursively check nested Pydantic models
        if _is_pydantic_model_type(ann):
            markers.extend(_extract_markers_from_pydantic_fields(ann, field_path))

    return markers


def _extract_markers_from_attrs_fields(attrs_cls: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Extract markers from attrs class fields.

    Args:
        attrs_cls: attrs class.
        prefix: Field name prefix for nested fields.

    Returns:
        List of (field_path, marker) tuples.
    """
    markers: list[tuple[str, str]] = []
    attrs_attrs = getattr(attrs_cls, "__attrs_attrs__", None)
    if not attrs_attrs:
        return markers

    for attr in attrs_attrs:
        field_name = attr.name
        field_path = f"{prefix}.{field_name}" if prefix else field_name
        ann = attr.type
        if ann:
            for meta in _annotation_markers(ann):
                if meta in _MARKER_TO_CATEGORY or meta in (RECORD_TRIGGER, CRATE_DIR):
                    markers.append((field_path, meta))

        # Recursively check nested attrs classes
        if _is_attrs_type(ann):
            markers.extend(_extract_markers_from_attrs_fields(ann, field_path))

    return markers


def _is_pydantic_model_type(ann: Any) -> bool:
    """Check if an annotation is a Pydantic BaseModel class."""
    try:
        from pydantic import BaseModel

        return isinstance(ann, type) and issubclass(ann, BaseModel)
    except (ImportError, TypeError):
        return False


def _is_attrs_type(ann: Any) -> bool:
    """Check if an annotation is an attrs class."""
    try:
        import attrs

        return isinstance(ann, type) and attrs.has(ann)
    except (ImportError, TypeError):
        return False


def _collect_ios_from_argument_collection(
    collection: ArgumentCollection,
    ios: IOArgumentNames,
    record_trigger_name: str | None,
    crate_dir_name: str | None,
) -> tuple[str | None, str | None]:
    """Collect IO markers and record trigger from an argument collection.

    Args:
        collection: Argument collection to inspect.
        ios: IO marker accumulator.
        record_trigger_name: Current record trigger name, if any.
        crate_dir_name: Current crate dir argument name, if any.

    Returns:
        Updated record trigger name and crate dir argument name.
    """
    for arg in collection:
        name = arg.name.lstrip("-")
        ann = arg.field_info.annotation
        markers = _annotation_markers(ann)
        if not markers:
            continue
        for meta in markers:
            if meta in _MARKER_TO_CATEGORY:
                getattr(ios, _MARKER_TO_CATEGORY[meta]).append(name)
            elif meta == RECORD_TRIGGER and record_trigger_name is None:
                record_trigger_name = name
            elif meta == CRATE_DIR and crate_dir_name is None:
                crate_dir_name = arg.field_info.names[0]

    return record_trigger_name, crate_dir_name


def _collect_ios_from_bound_value(
    value: Any,
    ios: IOArgumentNames,
    record_trigger_name: str | None,
    crate_dir_name: str | None,
    prefix: str = "",
) -> tuple[str | None, str | None]:
    """Collect IO markers and record trigger from a bound argument value.

    Args:
        value: Bound argument value to inspect.
        ios: IO marker accumulator.
        record_trigger_name: Current record trigger name, if any.
        crate_dir_name: Current crate dir argument name, if any.
        prefix: Optional field prefix for nested models.

    Returns:
        Updated record trigger name and crate dir argument name.
    """
    if _is_pydantic_model(value):
        model_cls = type(value)
        markers = _extract_markers_from_pydantic_fields(model_cls, prefix)
        for field_path, meta in markers:
            if meta in _MARKER_TO_CATEGORY:
                getattr(ios, _MARKER_TO_CATEGORY[meta]).append(field_path)
            elif meta == RECORD_TRIGGER and record_trigger_name is None:
                record_trigger_name = field_path
            elif meta == CRATE_DIR and crate_dir_name is None:
                crate_dir_name = field_path

    if _is_attrs_instance(value):
        attrs_cls = type(value)
        markers = _extract_markers_from_attrs_fields(attrs_cls, prefix)
        for field_path, meta in markers:
            if meta in _MARKER_TO_CATEGORY:
                getattr(ios, _MARKER_TO_CATEGORY[meta]).append(field_path)
            elif meta == RECORD_TRIGGER and record_trigger_name is None:
                record_trigger_name = field_path
            elif meta == CRATE_DIR and crate_dir_name is None:
                crate_dir_name = field_path

    return record_trigger_name, crate_dir_name


def _collect_ios_from_bound_arguments(
    bound_args: inspect.BoundArguments,
    ios: IOArgumentNames,
    record_trigger_name: str | None,
    crate_dir_name: str | None,
) -> tuple[str | None, str | None]:
    """Collect IO markers and record trigger from parsed bound arguments.

    Args:
        bound_args: Parsed Cyclopts bound arguments.
        ios: IO marker accumulator.
        record_trigger_name: Current record trigger name, if any.
        crate_dir_name: Current crate dir argument name, if any.

    Returns:
        Updated record trigger name and crate dir argument name.
    """
    for arg_value in bound_args.arguments.values():
        record_trigger_name, crate_dir_name = _collect_ios_from_bound_value(
            arg_value,
            ios,
            record_trigger_name,
            crate_dir_name,
        )

    return record_trigger_name, crate_dir_name


def _detect_ios_and_trigger(
    argument_collection: ArgumentCollection,
    command: Any | None = None,
    meta_argument_collection: ArgumentCollection | None = None,
    bound_args: inspect.BoundArguments | None = None,
) -> tuple[IOArgumentNames, str | None, str | None]:
    """Auto-detect input/output arguments and optional record trigger from Annotated metadata.

    Args:
        argument_collection: Assembled Cyclopts argument collection.
        command: The command function to check for *args.
        meta_argument_collection: Optional meta app argument collection to check for triggers.

    Returns:
        A tuple of (IOArgumentNames, trigger_arg_name_or_None, crate_dir_arg_name_or_None).
    """
    ios = IOArgumentNames()
    record_trigger_name: str | None = None
    crate_dir_name: str | None = None

    record_trigger_name, crate_dir_name = _collect_ios_from_argument_collection(
        argument_collection,
        ios,
        record_trigger_name,
        crate_dir_name,
    )

    if meta_argument_collection is not None:
        record_trigger_name, crate_dir_name = _collect_ios_from_argument_collection(
            meta_argument_collection,
            ios,
            record_trigger_name,
            crate_dir_name,
        )

    if command is not None and inspect.isfunction(command):
        sig = inspect.signature(command)
        for param_name, param in sig.parameters.items():
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                ann = param.annotation
                if hasattr(ann, "__metadata__"):
                    for meta in ann.__metadata__:
                        if meta in _MARKER_TO_CATEGORY:
                            getattr(ios, _MARKER_TO_CATEGORY[meta]).append(param_name)
                        elif meta == RECORD_TRIGGER:
                            if record_trigger_name is None:
                                record_trigger_name = param_name
                        elif meta == CRATE_DIR:
                            if crate_dir_name is None:
                                crate_dir_name = param_name

    if bound_args is not None:
        record_trigger_name, crate_dir_name = _collect_ios_from_bound_arguments(
            bound_args,
            ios,
            record_trigger_name,
            crate_dir_name,
        )

    return ios, record_trigger_name, crate_dir_name


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


def _resolve_executed_subapp(app: App, command: Any) -> App | None:
    """Find the app node that owns the executed default command.

    Args:
        app: App node to inspect.
        command: Resolved callable returned by ``parse_args``.

    Returns:
        Matching app instance, or None when no match is found.
    """
    if app.default_command is command:
        return app

    for subapp in app.subapps:
        resolved = _resolve_executed_subapp(subapp, command)
        if resolved is not None:
            return resolved

    return None


def _parse_tokens(tokens: str | Iterable[str] | None = None) -> list[str]:
    if tokens is None:
        return sys.argv[1:]
    elif isinstance(tokens, str):
        return shlex.split(tokens)
    return list(tokens)


def _is_successful_system_exit(error: SystemExit) -> bool:
    """Return whether a SystemExit represents a successful exit."""
    code = error.code
    if code is None:
        return True
    if isinstance(code, int):
        return code == 0
    return False


@dataclass
class Info:
    program: Program
    ioargs: IOArgumentPaths
    should_record: bool
    crate_dir: Path | None = None
    argv: list[str] | None = None


def collect_info(
    app: App,
    tokens: str | Iterable[str] | None = None,
    software_version: str | None = None,
) -> Info:
    program = program_from_app(app)
    if software_version is not None:
        program.version = software_version

    argv = _parse_tokens(tokens)
    command, bound_args, _ = app.parse_args(argv)
    bound_args.apply_defaults()
    executed_app = _resolve_executed_subapp(app, command) or app
    if executed_app.default_command is None:
        return Info(program=program, ioargs=IOArgumentPaths(), should_record=False, argv=argv)
    argument_collection = executed_app.assemble_argument_collection(parse_docstring=True)
    meta_argument_collection = None
    if hasattr(app.meta, "default_command") and app.meta.default_command:
        meta_argument_collection = app.meta.assemble_argument_collection()

    ios, record_trigger_name, crate_dir_name = _detect_ios_and_trigger(
        argument_collection,
        command=command,
        meta_argument_collection=meta_argument_collection,
        bound_args=bound_args,
    )

    is_builtin_command = command in (
        app.help_print,
        app.version_print,
        app.install_completion,
    )
    if is_builtin_command:
        return Info(program=program, ioargs=IOArgumentPaths(), should_record=False, argv=argv)

    should_record = _should_record(bound_args, record_trigger_name)
    ioargs = _collect_ioargs(
        bound_args,
        ios,
        argument_collection,
    )
    crate_dir = None
    if crate_dir_name is not None:
        crate_dir_value = _lookup_argument_value(bound_args.arguments, crate_dir_name)
        crate_dir = _resolve_crate_dir_value(crate_dir_value, crate_dir_name)

    return Info(
        program=program,
        ioargs=ioargs,
        should_record=should_record,
        crate_dir=crate_dir,
        argv=argv,
    )


@contextmanager
def record_cyclopts(
    app: App,
    tokens: str | Iterable[str] | None = None,
    dataset_license: str | None = None,
    crate_dir: Path | None = None,
    software_version: str | None = None,
    current_user: str | None = None,
) -> Generator[App]:
    """Context manager to record a Cyclopts CLI invocation in an RO-Crate.

    Hint:
        Marker metadata (for example :data:`INPUT_FILE` and :data:`OUTPUT_FILE`)
        is auto-detected from ``typing.Annotated`` parameters and nested models.
        Recording writes ``ro-crate-metadata.json`` only when execution finishes
        successfully and recording is enabled.

    Examples:
        Full runnable example:
        https://github.com/i-VRESSE/rocrate-action-recorder/tree/main/example/cyclopts

        Basic positional input/output tracking::

            from pathlib import Path
            from typing import Annotated

            from cyclopts import App
            from rocrate_action_recorder.adapters.cyclopts import (
                INPUT_FILE,
                OUTPUT_FILE,
                record_cyclopts,
            )

            app = App(version="1.2.3")

            @app.default
            def main(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                /,
            ):
                output.write_text(input.read_text().upper())

            # Call as: myscript.py input.txt output.txt
            with record_cyclopts(app, dataset_license="CC-BY-4.0"):
                app()

        Toggle recording with a boolean trigger flag::

            from typing import Annotated

            from cyclopts import App, Parameter
            from rocrate_action_recorder.adapters.cyclopts import RECORD_TRIGGER, record_cyclopts

            app = App()

            @app.default
            def main(*, prov: Annotated[bool, Parameter(negative=""), RECORD_TRIGGER] = False):
                pass

            # Records only when --prov is passed.
            # Call as: myscript.py --prov
            with record_cyclopts(app):
                app()

        Track nested configuration fields (for example dataclass or Pydantic models)::

            from dataclasses import dataclass
            from pathlib import Path
            from typing import Annotated

            from cyclopts import App
            from rocrate_action_recorder.adapters.cyclopts import INPUT_FILE, OUTPUT_FILE, record_cyclopts

            @dataclass
            class IO:
                input: Annotated[Path, INPUT_FILE]
                output: Annotated[Path, OUTPUT_FILE]

            app = App()

            @app.default
            def main(io: IO):
                io.output.write_text(io.input.read_text().upper())

            # Call as: myscript.py input.txt output.txt
            with record_cyclopts(app):
                app()

        Record multiple inputs/outputs from list markers::

            from pathlib import Path
            from typing import Annotated

            from cyclopts import App
            from rocrate_action_recorder.adapters.cyclopts import (
                INPUT_FILES,
                OUTPUT_FILES,
                record_cyclopts,
            )

            app = App()

            @app.default
            def main(
                *,
                inputs: Annotated[list[Path], INPUT_FILES],
                outputs: Annotated[list[Path], OUTPUT_FILES],
            ):
                for src, dst in zip(inputs, outputs, strict=True):
                    dst.write_text(src.read_text().upper())

            # Call as: myscript.py --inputs in1.txt --inputs in2.txt --outputs out1.txt --outputs out2.txt
            with record_cyclopts(app):
                app()

        Let CLI arguments choose the crate destination using :data:`CRATE_DIR`::

            from pathlib import Path
            from typing import Annotated

            from cyclopts import App
            from rocrate_action_recorder.adapters.cyclopts import CRATE_DIR, record_cyclopts

            app = App()

            @app.default
            def main(*, session_dir: Annotated[Path, CRATE_DIR]):
                pass

            # The CRATE_DIR-marked value overrides record_cyclopts(crate_dir=...).
            # Call as: myscript.py --session-dir ./runs/session-001
            with record_cyclopts(app, crate_dir=Path("fallback-crate")):
                app()

        Subcommands are supported; wrap the root app once and invoke normally::

            app = App(name="tool")
            process = App(name="process")

            @process.default
            def run(...):
                ...

            app.command(process)
            # Call as: tool process
            with record_cyclopts(app):
                app()

    Args:
        app: Root Cyclopts App instance.
        tokens: Optional command arguments used for parsing and action id generation.
        dataset_license: Optional dataset license string. If absent ro-crate will be invalid.
        crate_dir: Optional path to RO-Crate directory.
            If a parsed argument is annotated with :data:`CRATE_DIR`, that value takes precedence.
        software_version: Optional software version override. Otherwise extracted from App instance.
        current_user: Optional user override. Uses current system user if None.
    """
    start_time = datetime.now(tz=UTC)
    info = collect_info(app, tokens, software_version=software_version)

    try:
        yield app
    except SystemExit as error:
        if not _is_successful_system_exit(error):
            info.should_record = False
            raise
    except Exception:
        info.should_record = False
        raise
    finally:
        if info.should_record:
            end_time = datetime.now(tz=UTC)
            record(
                program=info.program,
                ioargs=info.ioargs,
                start_time=start_time,
                crate_dir=info.crate_dir or crate_dir,
                argv=[info.program.name] + (info.argv or []),
                end_time=end_time,
                current_user=current_user,
                dataset_license=dataset_license,
            )
