import argparse
import getpass
import importlib.metadata
import os
import sys
from datetime import datetime
from pathlib import Path

from rocrate.rocrate import ROCrate
from rocrate.model.person import Person
from rocrate.model.softwareapplication import SoftwareApplication


def record(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
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
        args: Parsed arguments for the CLI. The names in `inputs` and
            `outputs` must correspond to attributes on this namespace that
            point to files on disk.
        parser: The argparse parser that defines the CLI. Its `prog` and
            `description` populate crate metadata. Action `dest` names should
            match the entries in `inputs`/`outputs`.
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
            Determined from installed metadata for `parser.prog` when possible.
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

    if software_version is None:
        try:
            software_version = importlib.metadata.version(parser.prog)
        except Exception:
            # TODO try to determine package from calller frame?
            software_version = None

    if end_time is None:
        raise ValueError("end_time could not be determined")

    def _relpath(path: Path) -> Path:
        path = Path(path)
        try:
            rel = path.relative_to(crate_root)
        except ValueError:
            rel = Path(os.path.relpath(path, crate_root))
        return rel

    def find_action(k: str):
        for action in parser._actions:
            if action.dest == k:
                return action
        return None

    def to_file(o: str):
        path = getattr(args, o, None)
        if not isinstance(path, Path):
            raise ValueError(f"Expected Path for argument '{o}', got {type(path)}")
        rpath = _relpath(path)
        action_obj = find_action(o)
        name = action_obj.help if action_obj is not None else o
        return crate.add_file(
            source=path,
            dest_path=str(rpath),
            properties={
                "name": name,
                "contentSize": str(path.stat().st_size),
                "encodingFormat": "text/plain",  # TODO pass as arg or detect MIME type
            },
        )

    source = crate_root / "ro-crate-metadata.json"
    if not source.exists():
        source = None
    crate = ROCrate(source)

    agent = crate.add(Person(crate, current_user, properties={"name": current_user}))

    software = crate.add(
        SoftwareApplication(
            crate,
            parser.prog,
            properties={
                "name": parser.prog,
                "description": parser.description,
                "version": software_version,
            },
        )
    )

    objects = [to_file(o) for o in inputs]
    results = [to_file(o) for o in outputs]

    crate.add_action(
        instrument=software,
        identifier=action_id,
        object=objects,
        result=results,
        properties={
            "name": parser.description or parser.prog,
            "startTime": start_time.isoformat(),
            "endTime": end_time.isoformat(),
            "agent": agent,
        },
    )

    # Set root dataset properties
    crate.name = f"{parser.prog} actions"
    crate.description = parser.description or f"Calls to {parser.prog}"
    crate.datePublished = end_time.date()
    if dataset_license is not None:
        crate.license = dataset_license

    crate.metadata.write(crate_root)
    return crate_root / "ro-crate-metadata.json"
