"""Adapter for Cyclopts CLI framework."""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
import inspect
import logging
import shlex
import sys
from dataclasses import dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, LiteralString

from cyclopts import App
from cyclopts.argument import ArgumentCollection
from cyclopts.help import format_doc
from cyclopts.help.inline_text import InlineText

from rocrate_action_recorder.adapters.shared import (
    IOArgumentNames,
)
from rocrate_action_recorder.adapters.shared import (
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


def _collect_subcommands(
    app: App, parent_name: str, seen: set[str] | None = None
) -> dict[str, Program]:
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

        sub_app_name = (
            " ".join(sub_app.name)
            if isinstance(sub_app.name, tuple)
            else (sub_app.name or "")
        )
        cmd_name = sub_app_name

        # Check if this sub_app has a default command that is a function
        if sub_app.default_command and inspect.isfunction(sub_app.default_command):
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

    parent_name = (
        " ".join(app.name) if isinstance(app.name, tuple) else (app.name or "")
    )
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

    def search(value: Any) -> Any | None:
        if value is None:
            return None

        if is_dataclass(value):
            if hasattr(value, field_name):
                return getattr(value, field_name)
            for nested_name in value.__dataclass_fields__:
                resolved = search(getattr(value, nested_name))
                if resolved is not None:
                    return resolved
            return None

        if _is_pydantic_model(value):
            if hasattr(value, field_name):
                return getattr(value, field_name)
            # Pydantic models have __fields__ (Pydantic v1) or model_fields (Pydantic v2)
            # Access from class to avoid deprecation warning in Pydantic v2.11+
            model_cls = type(value)
            fields = getattr(model_cls, "model_fields", None) or getattr(
                model_cls, "__fields__", None
            )
            if fields:
                for nested_name in fields:
                    resolved = search(getattr(value, nested_name))
                    if resolved is not None:
                        return resolved
            return None

        if _is_attrs_instance(value):
            if hasattr(value, field_name):
                return getattr(value, field_name)
            # attrs instances have __attrs_attrs__
            attrs_attrs = getattr(type(value), "__attrs_attrs__", None)
            if attrs_attrs:
                for attr in attrs_attrs:
                    nested_name = attr.name
                    resolved = search(getattr(value, nested_name))
                    if resolved is not None:
                        return resolved
            return None

        # Handle tuples (e.g., from *args)
        if isinstance(value, tuple):
            for item in value:
                resolved = search(item)
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

    # Handle dataclass
    elif is_dataclass(value):
        if hasattr(value, current_field):
            current_value = getattr(value, current_field)
        else:
            return None
    # Handle Pydantic model
    elif _is_pydantic_model(value):
        if hasattr(value, current_field):
            current_value = getattr(value, current_field)
        else:
            return None
    # Handle attrs instance
    elif _is_attrs_instance(value):
        if hasattr(value, current_field):
            current_value = getattr(value, current_field)
        else:
            return None
    # Handle generic objects
    elif hasattr(value, current_field):
        current_value = getattr(value, current_field)
    else:
        return None

    # If there are more parts, recurse
    if len(parts) > 1:
        return _lookup_nested_field(current_value, parts[1])

    return current_value


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
            paths = value2paths(value)
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
    return ioargs


def _extract_markers_from_pydantic_fields(
    model_cls: Any, prefix: str = ""
) -> list[tuple[str, str]]:
    """Extract markers from Pydantic model fields.

    Args:
        model_cls: Pydantic model class.
        prefix: Field name prefix for nested fields.

    Returns:
        List of (field_path, marker) tuples.
    """
    markers: list[tuple[str, str]] = []
    fields = getattr(model_cls, "model_fields", None) or getattr(
        model_cls, "__fields__", None
    )
    if not fields:
        return markers

    for field_name, field_info in fields.items():
        field_path = f"{prefix}.{field_name}" if prefix else field_name
        ann = field_info.annotation

        # Recursively check nested Pydantic models
        if _is_pydantic_model_type(ann):
            markers.extend(_extract_markers_from_pydantic_fields(ann, field_path))

    return markers


def _extract_markers_from_attrs_fields(
    attrs_cls: Any, prefix: str = ""
) -> list[tuple[str, str]]:
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
        if ann and hasattr(ann, "__metadata__"):
            for meta in ann.__metadata__:
                if meta in _MARKER_TO_CATEGORY or meta == RECORD_TRIGGER:
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


def _detect_ios_and_trigger(
    argument_collection: ArgumentCollection,
    command: Any | None = None,
    meta_argument_collection: ArgumentCollection | None = None,
    bound_args: inspect.BoundArguments | None = None,
) -> tuple[IOArgumentNames, str | None]:
    """Auto-detect input/output arguments and optional record trigger from Annotated metadata.

    Args:
        argument_collection: Assembled Cyclopts argument collection.
        command: The command function to check for *args.
        meta_argument_collection: Optional meta app argument collection to check for triggers.

    Returns:
        A tuple of (IOArgumentNames, trigger_arg_name_or_None).
    """
    ios = IOArgumentNames()
    record_trigger_name: str | None = None

    def _collect_from_collection(collection: ArgumentCollection):
        nonlocal record_trigger_name
        for arg in collection:
            name = arg.name.lstrip("-")
            ann = arg.field_info.annotation
            if not hasattr(ann, "__metadata__"):
                continue
            for meta in ann.__metadata__:
                if meta in _MARKER_TO_CATEGORY:
                    getattr(ios, _MARKER_TO_CATEGORY[meta]).append(name)
                elif meta == RECORD_TRIGGER:
                    if record_trigger_name is None:
                        record_trigger_name = name

    def _collect_markers_from_bound_args(bound_args: inspect.BoundArguments):
        """Extract markers from bound arguments, including nested model fields."""
        nonlocal record_trigger_name

        def _process_value(value: Any, prefix: str = "") -> None:
            nonlocal record_trigger_name

            if _is_pydantic_model(value):
                model_cls = type(value)
                markers = _extract_markers_from_pydantic_fields(model_cls, prefix)
                for field_path, meta in markers:
                    if meta in _MARKER_TO_CATEGORY:
                        getattr(ios, _MARKER_TO_CATEGORY[meta]).append(field_path)
                    elif meta == RECORD_TRIGGER and record_trigger_name is None:
                        record_trigger_name = field_path

            if _is_attrs_instance(value):
                attrs_cls = type(value)
                markers = _extract_markers_from_attrs_fields(attrs_cls, prefix)
                for field_path, meta in markers:
                    if meta in _MARKER_TO_CATEGORY:
                        getattr(ios, _MARKER_TO_CATEGORY[meta]).append(field_path)
                    elif meta == RECORD_TRIGGER and record_trigger_name is None:
                        record_trigger_name = field_path

        for arg_value in bound_args.arguments.values():
            _process_value(arg_value)

    _collect_from_collection(argument_collection)

    if meta_argument_collection is not None:
        _collect_from_collection(meta_argument_collection)

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

    if bound_args is not None:
        _collect_markers_from_bound_args(bound_args)

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


@dataclass
class Info:
    program: Program
    ioargs: IOArgumentPaths
    should_record: bool
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
    executed_app = _resolve_executed_subapp(app, command) or app
    argument_collection = executed_app.assemble_argument_collection(
        parse_docstring=True
    )
    meta_argument_collection = None
    if hasattr(app.meta, "default_command") and app.meta.default_command:
        meta_argument_collection = app.meta.assemble_argument_collection()

    ios, record_trigger_name = _detect_ios_and_trigger(
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
        return Info(
            program=program, ioargs=IOArgumentPaths(), should_record=False, argv=argv
        )

    should_record = _should_record(bound_args, record_trigger_name)
    ioargs = _collect_ioargs(
        bound_args,
        ios,
        argument_collection,
    )

    return Info(program=program, ioargs=ioargs, should_record=should_record, argv=argv)


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
        The argument names passed in :class:`IOArgumentNames` should match keys in
        the bound arguments (typically from `app.parse_args()` or the decorated function
        arguments). For example `def myfunc(input: Path, output: Path)` would correspond
        to parameter names `input` and `output`.

    Args:
        app: Root Cyclopts App instance.
        tokens: Optional command arguments to use in action id.
        dataset_license: Optional dataset license string. If absent ro-crate will be invalid.
        crate_dir: Optional path to RO-Crate directory.
        software_version: Optional software version override. Otherwise extracted from App instance.
        current_user: Optional user override. Uses current system user if None.
    """
    start_time = datetime.now(tz=UTC)
    info = collect_info(app, tokens, software_version=software_version)

    yield app

    end_time = datetime.now(tz=UTC)
    if info.should_record:
        record(
            program=info.program,
            ioargs=info.ioargs,
            start_time=start_time,
            crate_dir=crate_dir,
            argv=[info.program.name] + (info.argv or []),
            end_time=end_time,
            current_user=current_user,
            dataset_license=dataset_license,
        )
