"""Core functionality for recording CLI invocations in RO-Crate format."""

from dataclasses import dataclass, field
from datetime import datetime
import getpass
import importlib.metadata
import mimetypes
import os
import pwd
from pathlib import Path
import shutil
import subprocess
import sys
from shlex import quote
import logging

from rocrate.model import File
from rocrate.model.dataset import Dataset
from rocrate.model.person import Person
from rocrate.model.creativework import CreativeWork
from rocrate.rocrate import Entity, ROCrate, SoftwareApplication, Metadata

logger = logging.getLogger(__name__)


@dataclass
class Program:
    """
    Attribute:
        name: Name of the program.
        description: Description of the program.
        subcommands: Dictionary of subcommand names to Program instances.
    """

    name: str
    description: str
    subcommands: dict[str, "Program"] = field(default_factory=dict)


@dataclass
class IOArgumentPath:
    """Container for the details of an input/output argument.

    Attributes:
        name: Name of the argument as in the parser.
        path: The value of the argument as a path.
        help: Help text associated with the argument.
    """

    name: str
    path: Path
    help: str


@dataclass
class IOArgumentPaths:
    """Container for all the input/output paths for a recording.

    Attributes:
        input_files: List of input file arguments.
        output_files: List of output file arguments.
        input_dirs: List of input directory arguments.
        output_dirs: List of output directory arguments.
    """

    input_files: list[IOArgumentPath]
    output_files: list[IOArgumentPath]
    input_dirs: list[IOArgumentPath]
    output_dirs: list[IOArgumentPath]


@dataclass
class SoftwareInfo:
    version: str | None = None
    homepage: str | None = None
    license: str | None = None


def detect_software_version(program_name: str) -> str:
    """Detect software version from package name or executable.

    Args:
        program_name: Name of the program/package or path to executable.

    Returns:
        Version string if found, otherwise empty string.
    """
    # try to use program name as package name
    try:
        software_version = importlib.metadata.version(program_name)
    except importlib.metadata.PackageNotFoundError:
        software_version = ""

    if not software_version:
        software_version = _dectect_version_by_running(program_name)

    if not software_version:
        # TODO try to determine package from caller frame?
        pass
    return software_version


def _dectect_version_by_running(program_name: str) -> str:
    """Try to detect version by running the program with --version flag.

    Args:
        program_name: Name of the program or path to executable.

    Returns:
        Version string if found, otherwise empty string.
    """
    # First try as a direct file path
    program_path = Path(program_name)
    if program_path.is_file() and os.access(program_path, os.X_OK):
        executable = str(program_path)
    else:
        # Try to find the program in PATH
        executable = shutil.which(program_name)
        if not executable:
            return ""

    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=5
        )
        if result.stdout:
            output = result.stdout.strip()
            # Remove script name from output by taking the last space-separated token
            parts = output.split()
            if len(parts) > 1:
                return parts[-1]
            else:
                return output
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass
    return ""


def map_argument_names2paths(
    argument_names: list[str], ioarguments: dict[str, list[IOArgumentPath]]
) -> list[IOArgumentPath]:
    """Collect IOArguments for the given argument names.

    Args:
        argument_names: List of argument names to match.
        ioarguments: Dictionary mapping argument names to lists of IOArguments.

    Returns:
        List of IOArgument objects for the matching argument names.
    """
    args = []
    for argument_name in argument_names:
        if argument_name in ioarguments:
            args.extend(ioarguments[argument_name])
    return args


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
    program: Program,
    ioargs: IOArgumentPaths,
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
        program: The program details.
        ioargs: Which files/directories are involved in action.
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
            For example "CC-BY-4.0".

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

    software_version = software_version or detect_software_version(program.name)

    if not dataset_license:
        logger.warning(
            "No dataset license specified for the RO-Crate. This will lead to invalid crates. Consider setting a license like 'CC-BY-4.0'."
        )

    return _record_run(
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


def add_software_application(
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


def add_file(crate: ROCrate, crate_root: Path, ioarg: IOArgumentPath) -> File:
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
        source=path,
        dest_path=identifier,
        properties={
            "name": identifier,
            "description": ioarg.help,
            "contentSize": path.stat().st_size,
            "encodingFormat": _get_mime_type(path),
        },
    )
    crate.add(file)
    return file


def add_files(
    crate: ROCrate, crate_root: Path, ioargs: list[IOArgumentPath]
) -> list[File]:
    """Add multiple files to the crate.

    Args:
        crate: The ROCrate object.
        crate_root: The root directory of the crate.
        ioargs: List of IOArgument objects.

    Returns:
        List of File objects.
    """
    return [add_file(crate, crate_root, ioarg) for ioarg in ioargs]


def add_dir(crate: ROCrate, crate_root: Path, ioarg: IOArgumentPath) -> Dataset:
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
    crate: ROCrate, crate_root: Path, ioargs: list[IOArgumentPath]
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
        # TODO add UpdateAction block with new inputs/outputs metadata and times?
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
    ioargs: IOArgumentPaths,
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


def _unique_by_id[T: Entity](entities: list[T]) -> list[T]:
    """Get unique entities based on their IDs.

    Args:
        entities: List of entities.

    Returns:
        List of unique entities.
    """
    seen_ids = set()
    unique_entities = []
    for entity in entities:
        if entity.id not in seen_ids:
            seen_ids.add(entity.id)
            unique_entities.append(entity)
    return unique_entities


def conform_to_process_run_crate_profile(crate: ROCrate) -> CreativeWork:
    """Makes crate conform to Process Run Crate profile

    See https://www.researchobject.org/workflow-run-crate/profiles/0.5/process_run_crate/

    Args:
        crate: The ROCrate object.
    Returns:
        The CreativeWork entity representing the Process Run Crate profile.
    """
    prc = CreativeWork(
        crate=crate,
        identifier="https://w3id.org/ro/wfrun/process/0.5",
        properties={
            "name": "Process Run Crate",
            "version": "0.5",
        },
    )

    if not crate.get(prc.id):
        crate.add(prc)

    if (
        "conformsTo" not in crate.root_dataset
        or crate.root_dataset["conformsTo"] != prc
    ):
        crate.root_dataset["conformsTo"] = prc
    if (
        "https://w3id.org/ro/terms/workflow-run/context"
        not in crate.metadata.extra_contexts
    ):
        crate.metadata.extra_contexts.append(
            "https://w3id.org/ro/terms/workflow-run/context"
        )
    return prc


def _update_crate(
    crate: ROCrate,
    crate_root: Path,
    program: Program,
    software_version: str,
    ioargs: IOArgumentPaths,
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
    conform_to_process_run_crate_profile(crate)

    software = add_software_application(crate, program, software_version)

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
        all_inputs=_unique_by_id(all_inputs),
        all_outputs=_unique_by_id(all_outputs),
        agent=agent,
    )

    if dataset_license:
        crate.license = dataset_license
    crate.datePublished = end_time

    if not crate.name:
        crate.name = f"Files used by {program.name}"
    if not crate.description:
        crate.description = f"An RO-Crate recording the files and directories that were used as input or output by {program.name}."

    return crate


def playback(crate_root: Path) -> str:
    """Extract and return recorded action commands sorted by execution time.

    Args:
        crate_root: Root directory of the RO-Crate.

    Returns:
        Newline-separated string of action command lines, sorted by endTime.
        Returns empty string if no actions are recorded.
    """
    metadata_file = crate_root / Metadata.BASENAME
    if not metadata_file.exists():
        return ""

    crate = ROCrate(crate_root)

    # Extract all CreateActions from the crate (supports UpdateActions when implemented)
    actions = []
    for action in crate.get_by_type("CreateAction"):
        props = action.properties()
        end_time_str = props.get("endTime", "")
        action_id = action.id
        if action_id and end_time_str:
            actions.append((end_time_str, action_id))

    # Sort by endTime
    actions.sort(key=lambda x: x[0])

    # Return newline-separated action IDs
    return "\n".join(action_id for _, action_id in actions)
