import getpass
import importlib.metadata
import mimetypes
import os
import sys
from datetime import datetime
from pathlib import Path

from rocrate.rocrate import ROCrate
from rocrate.model.person import Person
from rocrate.model.softwareapplication import SoftwareApplication

from .parser import Arguments, Parser


def record(
    args: Arguments,
    parser: Parser,
    start_time: datetime,
    input_files: list[str] | None = None,
    output_files: list[str] | None = None,
    input_dirs: list[str] | None = None,
    output_dirs: list[str] | None = None,
    crate_dir: Path | None = None,
    argv: list[str] | None = None,
    end_time: datetime | None = None,
    current_user: str | None = None,
    software_version: str | None = None,
    dataset_license: str | None = None,
) -> Path:
    """Record a CLI invocation as an RO-Crate.

    Creates a RO-Crate describing the execution of a CLI command, including
    the `Dataset`, `SoftwareApplication`, `Person`, `CreateAction`, and `File`
    entities derived from the provided parser, arguments, and I/O files. The
    crate is written as ro-crate-metadata.json in `crate_dir` (or the current
    working directory).

    Args:
        args: Parsed arguments from the CLI. The names in `input_files`,
            `output_files`, `input_dirs`, and `output_dirs` must correspond to
            argument names that point to files or directories on disk. Should
            implement the Arguments protocol.
        parser: The CLI parser that defines the program. Its program name and
            description populate crate metadata. Argument names should
            match the entries in `input_files`/`output_files`/`input_dirs`/`output_dirs`.
            Should implement the Parser protocol.
        start_time: Timestamp marking when the CLI execution began.
        input_files: Argument names to treat as input files (e.g., "input").
            Each must reference an existing file via `args`.
        output_files: Argument names to treat as output files (e.g., "output").
            Each must reference an existing file via `args`.
        input_dirs: Argument names to treat as input directories (e.g.,
            "input_dir"). Each must reference an existing directory via `args`.
        output_dirs: Argument names to treat as output directories (e.g.,
            "output_dir"). Each must reference an existing directory via `args`.
        crate_dir: Directory where the RO-Crate is created. Defaults to the
            current working directory.
        argv: Command-line tokens used to compose the `CreateAction.id`.
            Defaults to the current process arguments.
        end_time: Timestamp marking when the CLI execution finished. Defaults
            to the current UTC time.
        current_user: Username recorded as the `Person` agent. Auto-detected
            if omitted.
        software_version: Version string for the `SoftwareApplication`.
            Determined from installed metadata for the program name when
            possible.
        dataset_license: License identifier to record on the top-level
            `Dataset`.

    Returns:
        Path to the generated ro-crate-metadata.json file inside `crate_dir`.

    Raises:
        ValueError: If any name in `input_files`, `output_files`, `input_dirs`,
            or `output_dirs` does not resolve to a file or directory `Path` on
            `args`.
    """
    crate_root = Path(crate_dir or Path.cwd())
    crate_root.mkdir(parents=True, exist_ok=True)

    argv_list = list(argv) if argv is not None else list(sys.argv)
    # TODO handle args with spaces in them
    action_id = " ".join(argv_list)

    if input_files is None:
        input_files = []
    if output_files is None:
        output_files = []
    if input_dirs is None:
        input_dirs = []
    if output_dirs is None:
        output_dirs = []

    if current_user is None:
        try:
            import pwd

            current_user = pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            current_user = getpass.getuser()

    program_name = parser.get_program_name()
    program_description = parser.get_description()

    if software_version is None:
        try:
            software_version = importlib.metadata.version(program_name)
        except Exception:
            # TODO try to determine package from calller frame?
            software_version = None

    if end_time is None:
        end_time = datetime.now()

    def _get_mime_type(path: Path) -> str:
        """Detect MIME type from file path."""
        mime_type, _ = mimetypes.guess_type(str(path))
        return mime_type or "application/octet-stream"

    def _relpath(path: Path) -> Path:
        path = Path(path)
        try:
            return path.relative_to(crate_root)
        except ValueError as exc:
            raise ValueError(
                f"Path '{path}' is outside the crate root '{crate_root}'"
            ) from exc

    def _get_path(arg_name: str) -> Path:
        """Get and validate path from arguments."""
        path = args.get(arg_name)
        if not isinstance(path, Path):
            raise ValueError(
                f"Expected Path for argument '{arg_name}', got {type(path)}"
            )
        return path

    def _get_entity_name(arg_name: str) -> str |None:
        """Get display name for entity from argument help text."""
        arg_obj = parser.find_argument(arg_name)
        return arg_obj.help if arg_obj is not None else arg_name

    def _update_entity_properties(entity, updates: dict[str, str]) -> None:
        """Update properties on an existing entity."""
        props = getattr(entity, "properties", None)
        if isinstance(props, dict):
            props.update(updates)
        raw = getattr(entity, "_jsonld", None)
        if isinstance(raw, dict):
            raw.update(updates)

    def to_file(o: str):
        path = _get_path(o)
        rpath = _relpath(path)
        name = _get_entity_name(o)
        file_id = str(rpath)
        existing = getattr(crate, "get", None)
        entity = existing(file_id) if callable(existing) else None
        if entity is not None:
            props = {
                    "contentSize": str(path.stat().st_size),
                    "encodingFormat": _get_mime_type(path),
            }
            if name:
                props["name"] = name
            _update_entity_properties(
                entity,
                props,
            )
            return entity
        return crate.add_file(
            source=path,
            dest_path=file_id,
            properties={
                "name": name,
                "contentSize": str(path.stat().st_size),
                "encodingFormat": _get_mime_type(path),
            },
        )

    def to_dir(o: str):
        path = _get_path(o)
        rpath = _relpath(path)
        name = _get_entity_name(o)
        dir_id = str(rpath)
        existing = getattr(crate, "get", None)
        entity = existing(dir_id) if callable(existing) else None
        if entity is not None and name is not None:
            _update_entity_properties(entity, {"name": name})
            return entity
        return crate.add_directory(
            source=path,
            dest_path=dir_id,
            properties={
                "name": name,
            },
        )

    metadata_file = crate_root / "ro-crate-metadata.json"
    source_dir: Path | None = crate_root if metadata_file.exists() else None
    crate = ROCrate(source_dir)

    # De-duplicate Person and SoftwareApplication by @id if they already exist in the crate
    get_entity = getattr(crate, "get", None)
    agent = None
    if callable(get_entity):
        agent = get_entity(current_user)
    if agent is None:
        agent = crate.add(
            Person(crate, current_user, properties={"name": current_user})
        )

    software = None
    # Use versioned identifier if version is provided
    software_id = (
        f"{program_name}@{software_version}" if software_version else program_name
    )
    if callable(get_entity):
        software = get_entity(software_id)
    if software is None:
        software = crate.add(
            SoftwareApplication(
                crate,
                software_id,
                properties={
                    "name": program_name,
                    "description": program_description,
                    "version": software_version,
                },
            )
        )

    input_file_ids = [to_file(o) for o in input_files]
    output_file_ids = [to_file(o) for o in output_files]

    input_dir_ids = [to_dir(o) for o in input_dirs]
    output_dir_ids = [to_dir(o) for o in output_dirs]

    all_inputs = input_file_ids + input_dir_ids
    all_outputs = output_file_ids + output_dir_ids

    # Update existing action with the same identifier, otherwise add a new one
    # Always add the action; the RO-Crate library should upsert by identifier
    crate.add_action(
        instrument=software,
        identifier=action_id,
        object=all_inputs,
        result=all_outputs,
        properties={
            "name": program_description or program_name,
            "startTime": start_time.isoformat(),
            "endTime": end_time.isoformat(),
            "agent": agent,
        },
    )

    # Set root dataset properties
    crate.name = f"{program_name} actions"
    crate.description = program_description or f"Calls to {program_name}"
    crate.datePublished = end_time.date()
    if dataset_license is not None:
        crate.license = dataset_license

    crate.metadata.write(crate_root)
    return crate_root / "ro-crate-metadata.json"
