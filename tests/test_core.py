from datetime import UTC, datetime
import importlib.metadata
import json
from pathlib import Path
import subprocess

from pytest import LogCaptureFixture
import pytest

from rocrate_action_recorder.core import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    detect_software_version,
    playback,
    record,
)


def rocrate_validator(crate_dir: Path, severity: str = "required") -> list:
    # The validator takes ~2.6s on my machine, so use sparingly in tests

    # tried use https://github.com/crs4/rocrate-validator/tree/develop?tab=readme-ov-file#programmatic-validation
    # but did give issues for recommended severity even though crate is invalid
    # switch to using cli call instead
    cmd = [
        "rocrate-validator",
        "validate",
        "-v",
        "--output-format",
        "json",
        "--output-file",
        "report.json",
        "--requirement-severity",
        severity,
        "--output-line-width",  # Add otherwise string values are wrapped, causing incorrect JSON
        "100000",
    ]
    subprocess.run(cmd, cwd=crate_dir)

    with open(crate_dir / "report.json", encoding="utf-8") as f:
        report_body = f.read()
        report = json.loads(report_body)
        return report["issues"]


def assert_crate_contents(
    crate_meta: Path,
    program_name: str,
    end_time: datetime,
    has_part: list = [],
    custom_entities: list = [],
):
    """Assert that the crate metadata json file contains the expected entities.

    Args:
        crate_meta: Path to the ro-crate-metadata.json file.
        program_name: Name of the program recorded in the crate.
        end_time: End time of the program execution.
        has_part: List of entities that should be listed as parts of the dataset. Defaults to [].
        custom_entities: List of additional custom entities expected in the crate. Defaults to [].
    """
    expected = {
        "@context": [
            "https://w3id.org/ro/crate/1.1/context",
            "https://w3id.org/ro/terms/workflow-run/context",
        ],
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": end_time.isoformat(),
                "conformsTo": {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                },
                "license": "CC-BY-4.0",
                "name": f"Files used by {program_name}",
                "description": f"An RO-Crate recording the files and directories that were used as input or output by {program_name}.",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {
                    "@id": "./",
                },
                "conformsTo": {
                    "@id": "https://w3id.org/ro/crate/1.1",
                },
            },
            {
                "@id": "https://w3id.org/ro/wfrun/process/0.5",
                "@type": "CreativeWork",
                "name": "Process Run Crate",
                "version": "0.5",
            },
        ]
        + custom_entities,
    }
    if has_part:
        expected["@graph"][0]["hasPart"] = has_part
    actual = json.loads(crate_meta.read_text(encoding="utf-8"))
    assert actual == expected


def test_detect_software_version_caller():
    result = detect_software_version("non_existent_script_12345")

    expected = importlib.metadata.version("pytest")
    assert result == expected


def test_detect_software_version_scriptsameaspackage():
    result = detect_software_version("pytest")
    expected = importlib.metadata.version("pytest")
    assert result == expected


def test_detect_software_version_localscript(tmp_path: Path):
    # Create a dummy executable file
    exe_file = tmp_path / "dummy_executable.py"
    exe_file.write_text(
        "#!/usr/bin/env python\nimport sys\nif '--version' in sys.argv:\n    print('v4.2')\n"
    )
    exe_file.chmod(0o755)

    result = detect_software_version(str(exe_file))
    assert result == "v4.2"


def test_detect_software_version_localscriptstripped(tmp_path: Path):
    # Create a dummy executable file
    exe_file = tmp_path / "dummy_executable.py"
    exe_file.write_text(
        "#!/usr/bin/env python\nimport sys\nif '--version' in sys.argv:\n    print('dummy_executable.py v4.2')\n"
    )
    exe_file.chmod(0o755)

    result = detect_software_version(str(exe_file))
    assert result == "v4.2"


def test_detect_software_version_scriptinpath():
    # `rocrate-validator` script at `.venv/bin/rocrate-validator`
    # is from `roc-validator` package so cannot use importlib
    result = detect_software_version("rocrate-validator")
    expected = importlib.metadata.version("roc-validator")
    assert expected in result


def test_playback_empty_crate(tmp_path: Path):
    """Test playback returns empty string when no crate exists."""
    result = playback(tmp_path)
    assert result == ""


def test_playback_single_action(tmp_path: Path):
    """Test playback with a single recorded action."""
    crate_dir = tmp_path / "crate"
    crate_dir.mkdir()

    # Create input/output files
    input_file = crate_dir / "input.txt"
    output_file = crate_dir / "output.txt"
    input_file.write_text("test input")
    output_file.write_text("test output")

    # Create a valid RO-Crate with proper entities
    metadata = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-16T12:00:05+00:00",
                "hasPart": [{"@id": "input.txt"}, {"@id": "output.txt"}],
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
            {
                "@id": "myscript@1.0",
                "@type": "SoftwareApplication",
                "name": "myscript",
                "version": "1.0",
            },
            {
                "@id": "input.txt",
                "@type": "File",
                "name": "input.txt",
            },
            {
                "@id": "output.txt",
                "@type": "File",
                "name": "output.txt",
            },
            {
                "@id": "testuser",
                "@type": "Person",
                "name": "testuser",
            },
            {
                "@id": "myscript --somearg",
                "@type": "CreateAction",
                "agent": {"@id": "testuser"},
                "endTime": "2026-01-16T12:00:05+00:00",
                "instrument": {"@id": "myscript@1.0"},
                "object": [{"@id": "input.txt"}],
                "result": [{"@id": "output.txt"}],
                "startTime": "2026-01-16T12:00:00+00:00",
            },
        ],
    }

    metadata_file = crate_dir / "ro-crate-metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))

    result = playback(crate_dir)
    assert result == "myscript --somearg"


def test_playback_multiple_actions_sorted_by_endtime(tmp_path: Path):
    """Test playback returns multiple actions sorted by endTime."""
    crate_dir = tmp_path / "crate"
    crate_dir.mkdir()

    # Create input/output files
    (crate_dir / "data1.txt").write_text("data 1")
    (crate_dir / "data2.txt").write_text("data 2")
    (crate_dir / "result1.txt").write_text("result 1")
    (crate_dir / "result2.txt").write_text("result 2")

    # Create RO-Crate with multiple actions - add them out of order
    metadata = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-17T10:00:15+00:00",
                "hasPart": [
                    {"@id": "data1.txt"},
                    {"@id": "data2.txt"},
                    {"@id": "result1.txt"},
                    {"@id": "result2.txt"},
                ],
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
            {
                "@id": "analyzer@1.0",
                "@type": "SoftwareApplication",
                "name": "analyzer",
                "version": "1.0",
            },
            {
                "@id": "converter@1.0",
                "@type": "SoftwareApplication",
                "name": "converter",
                "version": "1.0",
            },
            {
                "@id": "data1.txt",
                "@type": "File",
                "name": "data1.txt",
            },
            {
                "@id": "data2.txt",
                "@type": "File",
                "name": "data2.txt",
            },
            {
                "@id": "result1.txt",
                "@type": "File",
                "name": "result1.txt",
            },
            {
                "@id": "result2.txt",
                "@type": "File",
                "name": "result2.txt",
            },
            {
                "@id": "user1",
                "@type": "Person",
                "name": "user1",
            },
            {
                "@id": "analyzer --arg1",
                "@type": "CreateAction",
                "agent": {"@id": "user1"},
                "endTime": "2026-01-17T10:00:15+00:00",
                "instrument": {"@id": "analyzer@1.0"},
                "object": [{"@id": "data1.txt"}],
                "result": [{"@id": "result1.txt"}],
                "startTime": "2026-01-17T10:00:10+00:00",
            },
            {
                "@id": "converter --arg2",
                "@type": "CreateAction",
                "agent": {"@id": "user1"},
                "endTime": "2026-01-17T10:00:05+00:00",
                "instrument": {"@id": "converter@1.0"},
                "object": [{"@id": "data2.txt"}],
                "result": [{"@id": "result2.txt"}],
                "startTime": "2026-01-17T10:00:00+00:00",
            },
        ],
    }

    metadata_file = crate_dir / "ro-crate-metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))

    result = playback(crate_dir)
    lines = result.split("\n")

    # Should be sorted by endTime (converter first at 10:00:05, analyzer second at 10:00:15)
    assert len(lines) == 2
    assert lines[0] == "converter --arg2"
    assert lines[1] == "analyzer --arg1"


class Test_record:
    def test_without_dataset_license(self, tmp_path: Path, caplog: LogCaptureFixture):
        crate_dir = tmp_path
        start_time = datetime(2026, 1, 18, 14, 30, 0)
        end_time = datetime(2026, 1, 28, 11, 42, 38, 0)

        record(
            program=Program(
                name="test_program", description="Test program", version="1.0.0"
            ),
            ioargs=IOArgumentPaths(),
            argv=["test_program"],
            current_user="test_user",
            start_time=start_time,
            end_time=end_time,
            crate_dir=crate_dir,
        )

        assert "No dataset license specified" in caplog.text

        issues = rocrate_validator(crate_dir)

        assert len(issues) == 1
        assert (
            "The Root Data Entity MUST have a `license` property (as specified by schema./org)."
            in issues[0]["message"]
        )

    def test_1inputfile_1outputfile_absolute_paths(self, tmp_path: Path):
        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        output_path = crate_dir / "output.txt"
        input_path.write_text("Hello World\n")
        argv = [
            "myscript",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        # Simulate the script's main operation
        output_path.write_text(input_path.read_text().upper())
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path, help="Output file")
                ],
            ),
            argv=argv,
            current_user="tester",
            start_time=start_time,
            end_time=end_time,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        issues = rocrate_validator(crate_dir)
        assert not issues

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[{"@id": "input.txt"}, {"@id": "output.txt"}],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 12,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {
                    "@id": "output.txt",
                    "@type": "File",
                    "contentSize": 12,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output.txt",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": f"myscript --input {input_path} --output {output_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path} --output {output_path}",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output.txt"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_1inputfile_relative_path(self, tmp_path: Path):
        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        input_path.write_text("Hello World\n")
        argv = [
            "myscript",
            "--input",
            str(input_path),
        ]
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
            ),
            argv=argv,
            current_user="tester",
            start_time=start_time,
            end_time=end_time,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[{"@id": "input.txt"}],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 12,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": f"myscript --input {input_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path}",
                    "object": [{"@id": "input.txt"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_2actions_different_files(self, tmp_path: Path):
        crate_dir = tmp_path
        # First action: input.txt -> output.txt
        input_path1 = crate_dir / "input1.txt"
        input_path1.write_text("File 1 Input\n")
        output_path1 = crate_dir / "output1.txt"
        output_path1.write_text(input_path1.read_text().upper())
        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)
        argv1 = [
            "myscript",
            "--input",
            str(input_path1),
            "--output",
            str(output_path1),
        ]

        record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path1, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path1, help="Output file")
                ],
            ),
            argv=argv1,
            current_user="tester",
            start_time=start_time1,
            end_time=end_time1,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        # Second action: input2.txt -> output2.txt
        input_path2 = crate_dir / "input2.txt"
        input_path2.write_text("File 2 Input\n")
        output_path2 = crate_dir / "output2.txt"
        output_path2.write_text(input_path2.read_text().upper())
        argv2 = [
            "myscript",
            "--input",
            str(input_path2),
            "--output",
            str(output_path2),
        ]
        start_time2 = datetime(2026, 1, 16, 12, 10, 0, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 12, 10, 7, tzinfo=UTC)
        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path2, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path2, help="Output file")
                ],
            ),
            argv=argv2,
            current_user="tester",
            start_time=start_time2,
            end_time=end_time2,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
        expected_entities = {
            "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                "https://w3id.org/ro/terms/workflow-run/context",
            ],
            "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "datePublished": "2026-01-16T12:10:07+00:00",
                    "hasPart": [
                        {"@id": "input1.txt"},
                        {"@id": "output1.txt"},
                        {"@id": "input2.txt"},
                        {"@id": "output2.txt"},
                    ],
                    "license": "CC-BY-4.0",
                    "conformsTo": {
                        "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    },
                    "name": "Files used by myscript",
                    "description": "An RO-Crate recording the files and directories that were used as input or output by myscript.",
                },
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"},
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                },
                {
                    "@id": "input1.txt",
                    "@type": "File",
                    "contentSize": 13,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input1.txt",
                },
                {
                    "@id": "output1.txt",
                    "@type": "File",
                    "contentSize": 13,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output1.txt",
                },
                {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    "@type": "CreativeWork",
                    "name": "Process Run Crate",
                    "version": "0.5",
                },
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": f"myscript --input {input_path1} --output {output_path1}",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": "2026-01-16T12:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path1} --output {output_path1}",
                    "object": [{"@id": "input1.txt"}],
                    "result": [{"@id": "output1.txt"}],
                    "startTime": "2026-01-16T12:00:00+00:00",
                },
                {
                    "@id": "input2.txt",
                    "@type": "File",
                    "contentSize": 13,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input2.txt",
                },
                {
                    "@id": "output2.txt",
                    "@type": "File",
                    "contentSize": 13,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output2.txt",
                },
                {
                    "@id": f"myscript --input {input_path2} --output {output_path2}",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": "2026-01-16T12:10:07+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path2} --output {output_path2}",
                    "object": [{"@id": "input2.txt"}],
                    "result": [{"@id": "output2.txt"}],
                    "startTime": "2026-01-16T12:10:00+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_2actions_shared_inputfile_relative_paths(self, tmp_path: Path):
        crate_dir = tmp_path
        # First action: input.txt -> output.txt
        input_path = crate_dir / "input.txt"
        input_path.write_text("File Input\n")
        output_path1 = crate_dir / "output1.txt"
        output_path1.write_text(input_path.read_text().upper())
        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)
        argv1 = [
            "myscript",
            "--input",
            str(input_path.name),
            "--output",
            str(output_path1.name),
        ]

        record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path1, help="Output file")
                ],
            ),
            argv=argv1,
            current_user="tester",
            start_time=start_time1,
            end_time=end_time1,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        # Second action: input.txt -> output2.txt
        output_path2 = crate_dir / "output2.txt"
        output_path2.write_text(input_path.read_text().upper())
        argv2 = [
            "myscript",
            "--input",
            str(input_path.name),
            "--output",
            str(output_path2.name),
        ]
        start_time2 = datetime(2026, 1, 16, 12, 10, 0, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 12, 10, 7, tzinfo=UTC)
        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path2, help="Output file")
                ],
            ),
            argv=argv2,
            current_user="tester",
            start_time=start_time2,
            end_time=end_time2,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
        expected_entities = {
            "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                "https://w3id.org/ro/terms/workflow-run/context",
            ],
            "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "conformsTo": {
                        "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    },
                    "datePublished": "2026-01-16T12:10:07+00:00",
                    "description": "An RO-Crate recording the files and directories that were used as "
                    "input or output by myscript.",
                    "hasPart": [
                        {
                            "@id": "input.txt",
                        },
                        {
                            "@id": "output1.txt",
                        },
                        {
                            "@id": "output2.txt",
                        },
                    ],
                    "license": "CC-BY-4.0",
                    "name": "Files used by myscript",
                },
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {
                        "@id": "./",
                    },
                    "conformsTo": {
                        "@id": "https://w3id.org/ro/crate/1.1",
                    },
                },
                {
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {
                    "@id": "output1.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output1.txt",
                },
                {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    "@type": "CreativeWork",
                    "name": "Process Run Crate",
                    "version": "0.5",
                },
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "tester",
                    "@type": "Person",
                    "name": "tester",
                },
                {
                    "@id": "myscript --input input.txt --output output1.txt",
                    "@type": "CreateAction",
                    "agent": {
                        "@id": "tester",
                    },
                    "endTime": "2026-01-16T12:00:05+00:00",
                    "instrument": {
                        "@id": "myscript@1.2.3",
                    },
                    "name": "myscript --input input.txt --output output1.txt",
                    "object": [
                        {
                            "@id": "input.txt",
                        },
                    ],
                    "result": [
                        {
                            "@id": "output1.txt",
                        },
                    ],
                    "startTime": "2026-01-16T12:00:00+00:00",
                },
                {
                    "@id": "output2.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output2.txt",
                },
                {
                    "@id": "myscript --input input.txt --output output2.txt",
                    "@type": "CreateAction",
                    "agent": {
                        "@id": "tester",
                    },
                    "endTime": "2026-01-16T12:10:07+00:00",
                    "instrument": {
                        "@id": "myscript@1.2.3",
                    },
                    "name": "myscript --input input.txt --output output2.txt",
                    "object": [
                        {
                            "@id": "input.txt",
                        },
                    ],
                    "result": [
                        {
                            "@id": "output2.txt",
                        },
                    ],
                    "startTime": "2026-01-16T12:10:00+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_2actions_same_command(self, tmp_path: Path):
        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        input_path.write_text("File Input\n")

        # First action
        output_path1 = crate_dir / "output1.txt"
        output_path1.write_text(input_path.read_text().upper())
        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)
        argv = [
            "myscript",
            "--input",
            str(input_path.name),
            "--output",
            str(output_path1.name),
        ]

        record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path1, help="Output file")
                ],
            ),
            argv=argv,
            current_user="tester",
            start_time=start_time1,
            end_time=end_time1,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        # Second action
        output_path2 = crate_dir / "output2.txt"
        output_path2.write_text(input_path.read_text().upper())
        start_time2 = datetime(2026, 1, 16, 12, 10, 0, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 12, 10, 7, tzinfo=UTC)
        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path2, help="Output file")
                ],
            ),
            argv=argv,
            current_user="tester",
            start_time=start_time2,
            end_time=end_time2,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
        expected_entities = {
            "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                "https://w3id.org/ro/terms/workflow-run/context",
            ],
            "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "conformsTo": {"@id": "https://w3id.org/ro/wfrun/process/0.5"},
                    "datePublished": "2026-01-16T12:10:07+00:00",
                    "description": "An RO-Crate recording the files and directories that were used as input or output by myscript.",
                    "hasPart": [
                        {"@id": "input.txt"},
                        {"@id": "output1.txt"},
                        {"@id": "output2.txt"},
                    ],
                    "license": "CC-BY-4.0",
                    "name": "Files used by myscript",
                },
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"},
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                },
                {
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {
                    "@id": "output1.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output1.txt",
                },
                {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    "@type": "CreativeWork",
                    "name": "Process Run Crate",
                    "version": "0.5",
                },
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": "myscript --input input.txt --output output1.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": "2026-01-16T12:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input input.txt --output output1.txt",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output1.txt"}],
                    "startTime": "2026-01-16T12:00:00+00:00",
                },
                {
                    "@id": "output2.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output2.txt",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_2actions_same_command_different_versions(self, tmp_path: Path):
        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        input_path.write_text("File Input\n")

        # First action
        output_path1 = crate_dir / "output1.txt"
        output_path1.write_text(input_path.read_text().upper())
        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)
        argv1 = [
            "myscript",
            "--input",
            str(input_path.name),
            "--output",
            str(output_path1.name),
        ]

        record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path1, help="Output file")
                ],
            ),
            argv=argv1,
            current_user="tester",
            start_time=start_time1,
            end_time=end_time1,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        # Second action
        output_path2 = crate_dir / "output2.txt"
        output_path2.write_text(input_path.read_text().upper())
        start_time2 = datetime(2026, 1, 16, 12, 10, 0, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 12, 10, 7, tzinfo=UTC)
        argv2 = [
            "myscript",
            "--input",
            str(input_path.name),
            "--output",
            str(output_path2.name),
        ]

        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="2.0.0"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
                output_files=[
                    IOArgumentPath(name="output", path=output_path2, help="Output file")
                ],
            ),
            argv=argv2,
            current_user="tester",
            start_time=start_time2,
            end_time=end_time2,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
        expected_entities = {
            "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                "https://w3id.org/ro/terms/workflow-run/context",
            ],
            "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "conformsTo": {"@id": "https://w3id.org/ro/wfrun/process/0.5"},
                    "datePublished": "2026-01-16T12:10:07+00:00",
                    "description": "An RO-Crate recording the files and directories that were used as input or output by myscript.",
                    "hasPart": [
                        {"@id": "input.txt"},
                        {"@id": "output1.txt"},
                        {"@id": "output2.txt"},
                    ],
                    "license": "CC-BY-4.0",
                    "name": "Files used by myscript",
                },
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"},
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                },
                {
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {
                    "@id": "output1.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output1.txt",
                },
                {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    "@type": "CreativeWork",
                    "name": "Process Run Crate",
                    "version": "0.5",
                },
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": "myscript --input input.txt --output output1.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": "2026-01-16T12:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input input.txt --output output1.txt",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output1.txt"}],
                    "startTime": "2026-01-16T12:00:00+00:00",
                },
                {
                    "@id": "myscript@2.0.0",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "2.0.0",
                },
                {
                    "@id": "output2.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output2.txt",
                },
                {
                    "@id": "myscript --input input.txt --output output2.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": "2026-01-16T12:10:07+00:00",
                    "instrument": {"@id": "myscript@2.0.0"},
                    "name": "myscript --input input.txt --output output2.txt",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output2.txt"}],
                    "startTime": "2026-01-16T12:10:00+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_2actions_diff_commands(self, tmp_path: Path):
        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        input_path.write_text("File Input\n")

        # First action
        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)
        argv = [
            "myscript",
            "--input",
            str(input_path.name),
        ]

        record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path, help="Input file")
                ],
            ),
            argv=argv,
            current_user="tester",
            start_time=start_time1,
            end_time=end_time1,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        # Second action
        input_path2 = crate_dir / "input2.txt"
        input_path2.write_text("Another File Input\n")
        start_time2 = datetime(2026, 1, 16, 12, 10, 0, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 12, 10, 7, tzinfo=UTC)
        crate_meta = record(
            program=Program(
                name="myotherscript",
                description="My other test script",
                version="0.9.8",
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(name="input", path=input_path2, help="Input file")
                ],
            ),
            argv=[
                "myotherscript",
                "--input",
                str(input_path.name),
            ],
            current_user="tester",
            start_time=start_time2,
            end_time=end_time2,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
        expected_entities = {
            "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                "https://w3id.org/ro/terms/workflow-run/context",
            ],
            "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "conformsTo": {"@id": "https://w3id.org/ro/wfrun/process/0.5"},
                    "datePublished": "2026-01-16T12:10:07+00:00",
                    "description": "An RO-Crate recording the files and directories that were used as input or output by myscript.",
                    "hasPart": [{"@id": "input.txt"}, {"@id": "input2.txt"}],
                    "license": "CC-BY-4.0",
                    "name": "Files used by myscript",
                },
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"},
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                },
                {
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 11,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    "@type": "CreativeWork",
                    "name": "Process Run Crate",
                    "version": "0.5",
                },
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": "myscript --input input.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": "2026-01-16T12:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input input.txt",
                    "object": [{"@id": "input.txt"}],
                    "startTime": "2026-01-16T12:00:00+00:00",
                },
                {
                    "@id": "myotherscript@0.9.8",
                    "@type": "SoftwareApplication",
                    "description": "My other test script",
                    "name": "myotherscript",
                    "version": "0.9.8",
                },
                {
                    "@id": "input2.txt",
                    "@type": "File",
                    "contentSize": 19,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input2.txt",
                },
                {
                    "@id": "myotherscript --input input.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": "2026-01-16T12:10:07+00:00",
                    "instrument": {"@id": "myotherscript@0.9.8"},
                    "name": "myotherscript --input input.txt",
                    "object": [{"@id": "input2.txt"}],
                    "startTime": "2026-01-16T12:10:00+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_inputdir_outputdir_relative_paths(self, tmp_path: Path):
        crate_dir = tmp_path
        input_dir = crate_dir / "input_dir"
        input_dir.mkdir()
        output_dir = crate_dir / "output_dir"
        output_dir.mkdir()
        argv = [
            "myscript",
            "--input-dir",
            str(input_dir.name),
            "--output-dir",
            str(output_dir.name),
        ]
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_dirs=[
                    IOArgumentPath(
                        name="input-dir", path=input_dir, help="Input directory"
                    )
                ],
                output_dirs=[
                    IOArgumentPath(
                        name="output-dir", path=output_dir, help="Output directory"
                    )
                ],
            ),
            argv=argv,
            current_user="tester",
            start_time=start_time,
            end_time=end_time,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[
                {"@id": "input_dir/"},
                {"@id": "output_dir/"},
            ],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "input_dir/",
                    "@type": "Dataset",
                    "description": "Input directory",
                    "name": "input_dir",
                },
                {
                    "@id": "output_dir/",
                    "@type": "Dataset",
                    "description": "Output directory",
                    "name": "output_dir",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": "myscript --input-dir input_dir --output-dir output_dir",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input-dir input_dir --output-dir output_dir",
                    "object": [{"@id": "input_dir/"}],
                    "result": [{"@id": "output_dir/"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_1inputdir_absolute_path(self, tmp_path: Path):
        crate_dir = tmp_path
        input_dir = crate_dir / "input_dir"
        input_dir.mkdir()
        argv = [
            "myscript",
            "--input-dir",
            str(input_dir),
        ]
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_dirs=[
                    IOArgumentPath(
                        name="input-dir", path=input_dir, help="Input directory"
                    )
                ],
            ),
            argv=argv,
            current_user="tester",
            start_time=start_time,
            end_time=end_time,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[
                {"@id": "input_dir/"},
            ],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "input_dir/",
                    "@type": "Dataset",
                    "description": "Input directory",
                    "name": "input_dir",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": f"myscript --input-dir {input_dir}",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input-dir {input_dir}",
                    "object": [{"@id": "input_dir/"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_1outputfile_in_nested_dir_relative_path(self, tmp_path: Path, monkeypatch):
        crate_dir = tmp_path
        nested_dir = crate_dir / "nested"
        nested_dir.mkdir()
        input_file = nested_dir / "input.txt"
        input_file.write_text("File 1 Input\n")

        # Change to crate directory so relative paths resolve correctly
        monkeypatch.chdir(crate_dir)

        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)
        argv1 = [
            "myscript",
            "--input",
            "nested/input.txt",
        ]
        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_files=[
                    IOArgumentPath(
                        name="input", path=Path("nested/input.txt"), help="Input file"
                    )
                ],
            ),
            argv=argv1,
            current_user="tester",
            start_time=start_time1,
            end_time=end_time1,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time1,
            has_part=[
                {"@id": "nested/input.txt"},
            ],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "nested/input.txt",
                    "@type": "File",
                    "contentSize": 13,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "nested/input.txt",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": "myscript --input nested/input.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": end_time1.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input nested/input.txt",
                    "object": [{"@id": "nested/input.txt"}],
                    "startTime": start_time1.isoformat(),
                },
            ],
        )

    def test_1inputdir_in_nested_dir_relative_path(self, tmp_path: Path, monkeypatch):
        crate_dir = tmp_path
        nested_dir = crate_dir / "nested"
        nested_dir.mkdir()
        input_dir = nested_dir / "input"
        input_dir.mkdir()

        # Change to crate directory so relative paths resolve correctly
        monkeypatch.chdir(crate_dir)

        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)
        argv1 = [
            "myscript",
            "--input",
            "nested/input",
        ]
        crate_meta = record(
            program=Program(
                name="myscript", description="My test script", version="1.2.3"
            ),
            ioargs=IOArgumentPaths(
                input_dirs=[
                    IOArgumentPath(
                        name="input", path=Path("nested/input"), help="Input dir"
                    )
                ],
            ),
            argv=argv1,
            current_user="tester",
            start_time=start_time1,
            end_time=end_time1,
            crate_dir=crate_dir,
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time1,
            has_part=[
                {"@id": "nested/input/"},
            ],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "My test script",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "nested/input/",
                    "@type": "Dataset",
                    "description": "Input dir",
                    "name": "nested/input",
                },
                {"@id": "tester", "@type": "Person", "name": "tester"},
                {
                    "@id": "myscript --input nested/input",
                    "@type": "CreateAction",
                    "agent": {"@id": "tester"},
                    "endTime": end_time1.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input nested/input",
                    "object": [{"@id": "nested/input/"}],
                    "startTime": start_time1.isoformat(),
                },
            ],
        )

    def test_inputfile_outside_of_crate(self, tmp_path):
        crate_dir = tmp_path / "mycrate"
        crate_dir.mkdir()
        input_path = tmp_path / "input.txt"
        output_path = crate_dir / "output.txt"
        input_path.write_text("Hello World\n")
        argv = [
            "myscript",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        # Simulate the script's main operation
        output_path.write_text(input_path.read_text().upper())
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        with pytest.raises(ValueError, match="is outside the crate root"):
            record(
                program=Program(
                    name="myscript", description="My test script", version="1.2.3"
                ),
                ioargs=IOArgumentPaths(
                    input_files=[
                        IOArgumentPath(name="input", path=input_path, help="Input file")
                    ],
                    output_files=[
                        IOArgumentPath(
                            name="output", path=output_path, help="Output file"
                        )
                    ],
                ),
                argv=argv,
                current_user="tester",
                start_time=start_time,
                end_time=end_time,
                crate_dir=crate_dir,
                dataset_license="CC-BY-4.0",
            )
