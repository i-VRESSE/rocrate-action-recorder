"""Core functionality for recording CLI invocations in RO-Crate format."""

from dataclasses import dataclass, field
from datetime import datetime
import getpass
import importlib.metadata
import mimetypes
import os
import pwd
from pathlib import Path
import sys
from shlex import quote

from rocrate.model import File
from rocrate.model.dataset import Dataset
from rocrate.model.person import Person
from rocrate.rocrate import ROCrate, SoftwareApplication, Metadata


@dataclass
class Program:
    name: str
    description: str


@dataclass
class IOArgument:
    name: str
    path: Path
    help: str


@dataclass
class Info:
    program: Program
    ioarguments: dict[str, IOArgument]


@dataclass
class IOs:
    input_files: list[str] = field(default_factory=list[str])
    output_files: list[str] = field(default_factory=list[str])
    input_dirs: list[str] = field(default_factory=list[str])
    output_dirs: list[str] = field(default_factory=list[str])


@dataclass
class IOArgs:
    input_files: list[IOArgument]
    output_files: list[IOArgument]
    input_dirs: list[IOArgument]
    output_dirs: list[IOArgument]


def detect_software_version(program_name: str) -> str:
    """Detect software version from package name.

    Args:
        program_name: Name of the program/package.

    Returns:
        Version string if found, otherwise empty string.
    """
    # try to use program name as package name
    software_version = importlib.metadata.version(program_name)
    if not software_version:
        # TODO try to determine package from calller frame?
        pass
    return software_version


def make_action_id(argv: list[str] | None = None) -> str:
    """Create an action ID from command-line arguments.

    Args:
        argv: Command-line arguments. If None, uses sys.argv.

    Returns:
        Quoted and joined command-line string.
    """
    argv_list = list(argv) if argv is not None else list(sys.argv)
    quoted_argv = [quote(arg) for arg in argv_list]
    action_id = " ".join(quoted_argv)
    return action_id


def record(
    info: Info,
    ios: IOs,
    start_time: datetime,
    crate_dir: Path | None = None,
    argv: list[str] | None = None,
    end_time: datetime | None = None,
    current_user: str | None = None,
    software_version: str | None = None,
    dataset_license: str | None = None,
) -> Path:
    """Record a CLI invocation in an RO-Crate.

    This is a low-level function, better use one of the adapter functions for specific
    argument parsing frameworks.
    For example use `record_with_argparse` for [argparse](https://docs.python.org/3/library/argparse.html).

    Args:
        info: The Info object with program details and IO arguments.
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
    """
    crate_root = Path(crate_dir or Path.cwd()).resolve().expanduser()
    crate_root.mkdir(parents=True, exist_ok=True)

    action_id = make_action_id(argv)

    if current_user is None:
        try:
            current_user = pwd.getpwuid(os.getuid()).pw_name
        except (KeyError, OSError, AttributeError):
            current_user = getpass.getuser()

    if end_time is None:
        end_time = datetime.now()

    software_version = software_version or detect_software_version(info.program.name)

    ioargs = IOArgs(
        input_files=[
            info.ioarguments[f] for f in ios.input_files if f in info.ioarguments
        ],
        output_files=[
            info.ioarguments[f] for f in ios.output_files if f in info.ioarguments
        ],
        input_dirs=[
            info.ioarguments[d] for d in ios.input_dirs if d in info.ioarguments
        ],
        output_dirs=[
            info.ioarguments[d] for d in ios.output_dirs if d in info.ioarguments
        ],
    )

    return _record_run(
        crate_root=crate_root,
        program=info.program,
        software_version=software_version,
        ioargs=ioargs,
        action_id=action_id,
        start_time=start_time,
        end_time=end_time,
        current_user=current_user,
        dataset_license=dataset_license,
    )


def build_software_application(
    crate: ROCrate, program: Program, software_version: str
) -> SoftwareApplication:
    """Build a SoftwareApplication object for the crate.

    Args:
        crate: The ROCrate object.
        program: The Program object with name and description.
        software_version: The version string.

    Returns:
        A SoftwareApplication object.
    """
    software_id = (
        f"{program.name}@{software_version}" if software_version else program.name
    )
    props = {
        "name": program.name,
        "description": program.description,
        "version": software_version,
    }
    software_app = SoftwareApplication(crate, software_id, properties=props)
    return software_app


def add_sofware_application(
    crate: ROCrate, program: Program, software_version: str
) -> SoftwareApplication:
    """Add or get a SoftwareApplication in the crate.

    Args:
        crate: The ROCrate object.
        program: The Program object.
        software_version: The version string.

    Returns:
        The SoftwareApplication object.
    """
    software_app = build_software_application(crate, program, software_version)
    sa = crate.get(software_app.id)
    props = sa.properties if sa and isinstance(sa.properties, dict) else {}
    same_version = sa and props.get("version") == software_version
    if not same_version:
        crate.add(software_app)
    return software_app


def add_agent(crate: ROCrate, current_user: str) -> Person:
    """Add or get a Person agent in the crate.

    Args:
        crate: The ROCrate object.
        current_user: Username of the agent.

    Returns:
        The Person object.
    """
    person = Person(crate, current_user, properties={"name": current_user})
    if not crate.get(current_user):
        crate.add(person)
    return person


def _get_mime_type(path: Path) -> str:
    """Detect MIME type from file path.

    Args:
        path: Path to the file.

    Returns:
        MIME type string, defaults to 'application/octet-stream'.
    """
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def get_relative_path(path: Path, root: Path) -> Path:
    """Get the relative path from root.

    Args:
        path: The absolute or relative path.
        root: The root directory.

    Returns:
        The relative path from root.

    Raises:
        ValueError: If path is outside the root.
    """
    apath = path.resolve().expanduser().absolute()
    try:
        rpath = apath.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path '{path}' is outside the crate root '{root}'") from exc
    return rpath


def add_file(crate: ROCrate, crate_root: Path, ioarg: IOArgument) -> File:
    """Add or update a File in the crate.

    Args:
        crate: The ROCrate object.
        crate_root: The root directory of the crate.
        ioarg: The IOArgument specifying the file.

    Returns:
        The File object.
    """
    path = ioarg.path
    rpath = get_relative_path(path, crate_root)
    identifier = str(rpath)
    existing_file = crate.get(identifier)
    if (
        existing_file
        and isinstance(existing_file, File)
        and isinstance(existing_file.properties, dict)
    ):
        existing_file.properties.update(
            {
                "description": ioarg.help,
                "contentSize": path.stat().st_size,
                "encodingFormat": _get_mime_type(path),
            }
        )
        return existing_file
    file = File(
        crate,
        identifier,
        properties={
            "name": identifier,
            "description": ioarg.help,
            "contentSize": path.stat().st_size,
            "encodingFormat": _get_mime_type(path),
        },
    )
    crate.add(file)
    return file


def add_files(crate: ROCrate, crate_root: Path, ioargs: list[IOArgument]) -> list[File]:
    """Add multiple files to the crate.

    Args:
        crate: The ROCrate object.
        crate_root: The root directory of the crate.
        ioargs: List of IOArgument objects.

    Returns:
        List of File objects.
    """
    return [add_file(crate, crate_root, ioarg) for ioarg in ioargs]


def add_dir(crate: ROCrate, crate_root: Path, ioarg: IOArgument) -> Dataset:
    """Add or get a Dataset (directory) in the crate.

    Args:
        crate: The ROCrate object.
        crate_root: The root directory of the crate.
        ioarg: The IOArgument specifying the directory.

    Returns:
        The Dataset object.
    """
    rpath = get_relative_path(ioarg.path, crate_root)
    identifier = str(rpath)
    existing_dir = crate.get(identifier)
    if existing_dir and isinstance(existing_dir, Dataset):
        return existing_dir
    ds = Dataset(
        crate,
        source=identifier,
        dest_path=identifier,
        properties={"name": identifier},
    )
    crate.add(ds)
    return ds


def add_dirs(
    crate: ROCrate, crate_root: Path, ioargs: list[IOArgument]
) -> list[Dataset]:
    """Add multiple directories to the crate.

    Args:
        crate: The ROCrate object.
        crate_root: The root directory of the crate.
        ioargs: List of IOArgument objects.

    Returns:
        List of Dataset objects.
    """
    return [add_dir(crate, crate_root, ioarg) for ioarg in ioargs]


def add_action(
    crate: ROCrate,
    action_id: str,
    start_time: datetime,
    end_time: datetime,
    software: SoftwareApplication,
    all_inputs: list[File | Dataset],
    all_outputs: list[File | Dataset],
    agent: Person,
) -> None:
    """Add an action to the crate.

    Args:
        crate: The ROCrate object.
        action_id: Unique identifier for the action.
        start_time: When the action started.
        end_time: When the action ended.
        software: The instrument (SoftwareApplication) used.
        all_inputs: List of input files/datasets.
        all_outputs: List of output files/datasets.
        agent: The Person who ran the action.
    """
    existing_action = crate.get(action_id)
    if existing_action:
        return

    crate.add_action(
        instrument=software,
        identifier=action_id,
        object=all_inputs,
        result=all_outputs,
        properties={
            "name": action_id,
            "startTime": start_time.isoformat(),
            "endTime": end_time.isoformat(),
            "agent": agent,
        },
    )


def _record_run(
    crate_root: Path,
    program: Program,
    software_version: str,
    ioargs: IOArgs,
    action_id: str,
    start_time: datetime,
    end_time: datetime,
    current_user: str,
    dataset_license: str | None = None,
) -> Path:
    """Internal function to record a run into an RO-Crate.

    Args:
        crate_root: Root directory of the crate.
        program: The Program object.
        software_version: Version string.
        ioargs: IOArgs with input/output files and directories.
        action_id: Unique action identifier.
        start_time: When the action started.
        end_time: When the action ended.
        current_user: Username of the user.
        dataset_license: Optional license for the dataset.

    Returns:
        Path to the ro-crate-metadata.json file.
    """
    metadata_file = crate_root / Metadata.BASENAME
    source_dir: Path | None = crate_root if metadata_file.exists() else None
    crate = ROCrate(source_dir)

    _update_crate(
        crate=crate,
        crate_root=crate_root,
        program=program,
        software_version=software_version,
        ioargs=ioargs,
        action_id=action_id,
        start_time=start_time,
        end_time=end_time,
        current_user=current_user,
        dataset_license=dataset_license,
    )

    crate.metadata.write(crate_root)
    return metadata_file


def _update_crate(
    crate: ROCrate,
    crate_root: Path,
    program: Program,
    software_version: str,
    ioargs: IOArgs,
    action_id: str,
    start_time: datetime,
    end_time: datetime,
    current_user: str,
    dataset_license: str | None,
) -> ROCrate:
    """Internal function to update a crate with all necessary entities.

    Args:
        crate: The ROCrate object.
        crate_root: Root directory.
        program: The Program object.
        software_version: Version string.
        ioargs: IOArgs with inputs/outputs.
        action_id: Unique action identifier.
        start_time: When the action started.
        end_time: When the action ended.
        current_user: Username.
        dataset_license: Optional license.

    Returns:
        The updated ROCrate object.
    """
    software = add_sofware_application(crate, program, software_version)

    all_inputs = add_files(crate, crate_root, ioargs.input_files) + add_dirs(
        crate, crate_root, ioargs.input_dirs
    )
    all_outputs = add_files(crate, crate_root, ioargs.output_files) + add_dirs(
        crate, crate_root, ioargs.output_dirs
    )

    agent = add_agent(crate, current_user)

    add_action(
        crate=crate,
        action_id=action_id,
        start_time=start_time,
        end_time=end_time,
        software=software,
        all_inputs=all_inputs,
        all_outputs=all_outputs,
        agent=agent,
    )

    if dataset_license:
        crate.license = dataset_license
    crate.datePublished = end_time
    return crate
