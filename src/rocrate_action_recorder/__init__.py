import argparse
import getpass
import importlib.metadata
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import msgspec
from msgspec_schemaorg.base import SchemaOrgBase
from msgspec_schemaorg.models import (
    CreativeWork,
    MediaObject,
    Person,
    SoftwareApplication,
    CreateAction,
    Thing,
    Dataset,
)
from rdflib.util import date_time


class ROCrateCFile(MediaObject):
    type: str = msgspec.field(default_factory=lambda: "File", name="@type")


class ROCrateCreativeWork(CreativeWork):
    conformsTo: SchemaOrgBase | None = None


def as_link[T: SchemaOrgBase](thing: T) -> T:
    if thing.id is None:
        raise ValueError("Thing must have an id to be converted to a link")
    return cast(T, SchemaOrgBase(id=thing.id))


def as_links[T: SchemaOrgBase](things: list[T]) -> list[T]:
    return [as_link(t) for t in things]


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
            software_version = None

    if end_time is None:
        end_time = date_time.now(timezone.utc)
    if end_time is None:
        raise ValueError("end_time could not be determined")

    def _relpath(path: Path) -> Path:
        path = Path(path)
        try:
            rel = path.relative_to(crate_root)
        except ValueError:
            rel = Path(os.path.relpath(path, crate_root))
        return rel

    person = Person(id=current_user, name=current_user)

    software_id = parser.prog
    software = SoftwareApplication(
        id=software_id,
        name=parser.prog,
        description=parser.description,
        version=software_version,
    )

    def find_action(k: str):
        for action in parser._actions:
            if action.dest == k:
                return action
        return None

    def to_file(o: str) -> ROCrateCFile:
        path = getattr(args, o, None)
        if not isinstance(path, Path):
            raise ValueError(f"Expected Path for argument '{o}', got {type(path)}")
        rpath = _relpath(path)
        action = find_action(o)
        name = action.help if action is not None else o
        return ROCrateCFile(
            id=str(rpath),
            name=name,
            contentSize=str(path.stat().st_size),
            encodingFormat="text/plain",  # TODO pass as arg or detect MIME type
        )

    # My IDE does not undstand that File is a CreativeWork subclass or Thing subclass,
    # so we need to cast here
    objects: list[Thing] = [to_file(o) for o in inputs]
    results: list[Thing] = [to_file(o) for o in outputs]
    file_entities = cast(list[CreativeWork], objects + results)

    action = CreateAction(
        id=action_id,
        name=parser.description or parser.prog,
        agent=as_link(person),
        instrument=as_link(software),
        startTime=start_time,
        endTime=end_time,
        object=as_links(objects),
        result=as_links(results),
    )

    dataset = Dataset(
        id="./",
        name=f"{parser.prog} actions",
        description=parser.description or f"Calls to {parser.prog}",
        datePublished=end_time.date(),
        license=dataset_license,
        hasPart=as_links(file_entities),
    )

    metadata = ROCrateCreativeWork(
        id="ro-crate-metadata.json",
        about=as_link(dataset),
        conformsTo=SchemaOrgBase(id="https://w3id.org/ro/crate/1.1"),
    )

    graph = [
        metadata,
        dataset,
        person,
        software,
        action,
    ] + file_entities

    crate = SchemaOrgBase(
        context="https://w3id.org/ro/crate/1.1/context",
        graph=graph,
    )

    out_path = crate_root / "ro-crate-metadata.json"
    json_bytes = msgspec.json.encode(crate)
    out_path.write_bytes(json_bytes)
    return out_path
