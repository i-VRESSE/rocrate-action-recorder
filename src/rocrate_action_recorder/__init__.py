import getpass
import importlib.metadata
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
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
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
        args: Parsed arguments from the CLI. The names in `inputs` and
            `outputs` must correspond to argument names that point to files
            on disk. Should implement the Arguments protocol.
        parser: The CLI parser that defines the program. Its program name and
            description populate crate metadata. Argument names should
            match the entries in `inputs`/`outputs`. Should implement the
            Parser protocol.
        start_time: Timestamp marking when the CLI execution began.
        inputs: Argument names to treat as inputs (e.g., "input"). Each must
            reference an existing file via `args`.
        outputs: Argument names to treat as outputs (e.g., "output"). Each
            must reference an existing file via `args`.
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
        ValueError: If any name in `inputs` or `outputs` does not resolve to a
            file `Path` on `args`.
    """
    crate_root = Path(crate_dir or Path.cwd())
    crate_root.mkdir(parents=True, exist_ok=True)

    argv_list = list(argv) if argv is not None else list(sys.argv)
    # TODO handle args with spaces in them
    action_id = " ".join(argv_list)

    if inputs is None:
        inputs = []
    if outputs is None:
        outputs = []

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

    def _relpath(path: Path) -> Path:
        path = Path(path)
        try:
            return path.relative_to(crate_root)
        except ValueError as exc:
            raise ValueError(
                f"Path '{path}' is outside the crate root '{crate_root}'"
            ) from exc

    def to_file(o: str):
        path = args.get(o)
        if not isinstance(path, Path):
            raise ValueError(f"Expected Path for argument '{o}', got {type(path)}")
        rpath = _relpath(path)
        arg_obj = parser.find_argument(o)
        name = arg_obj.help if arg_obj is not None else o
        file_id = str(rpath)
        existing = getattr(crate, "get", None)
        entity = existing(file_id) if callable(existing) else None
        if entity is not None:
            size_str = str(path.stat().st_size)
            props = getattr(entity, "properties", None)
            if isinstance(props, dict):
                props["name"] = name
                props["contentSize"] = size_str
                props["encodingFormat"] = "text/plain"
            raw = getattr(entity, "_jsonld", None)
            if isinstance(raw, dict):
                raw["name"] = name
                raw["contentSize"] = size_str
                raw["encodingFormat"] = "text/plain"
            return entity
        return crate.add_file(
            source=path,
            dest_path=file_id,
            properties={
                "name": name,
                "contentSize": str(path.stat().st_size),
                "encodingFormat": "text/plain",  # TODO pass as arg or detect MIME type
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

    objects = [to_file(o) for o in inputs]
    results = [to_file(o) for o in outputs]

    # Update existing action with the same identifier, otherwise add a new one
    # Always add the action; the RO-Crate library should upsert by identifier
    crate.add_action(
        instrument=software,
        identifier=action_id,
        object=objects,
        result=results,
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
