from argparse import ArgumentParser, FileType
import argparse
import json
from pathlib import Path
from datetime import UTC, datetime

import pytest
from rocrate_validator import services, models
from rocrate_validator.utils.uri import URI

from rocrate_action_recorder import record_with_argparse, IOs
from rocrate_action_recorder.adapters.argparse import (
    argparse_value2paths,
    argparse_info,
    version_from_parser,
)
from rocrate_action_recorder.core import Info, Program, IOArgument


@pytest.fixture
def sample_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="myscript", description="Example CLI")
    parser.add_argument("--input", type=Path, help="Input file")
    parser.add_argument("--output", type=Path, help="Output file")
    return parser


def assert_crate_shape(crate_dir: Path):
    settings = models.ValidationSettings(
        rocrate_uri=URI(crate_dir),
        # TODO use more comprehensive provenance-run-crate profile, see https://w3id.org/ro/wfrun/provenance
        # now uses process run crate profile, see https://www.researchobject.org/workflow-run-crate/profiles/0.5/process_run_crate/
        # TODO when running validator on cli and example with -m recommended it fails,
        # but here with same severity it passes? that is weird
        requirement_severity=models.Severity.REQUIRED,
        verbose=True,
    )
    result = services.validate(settings)
    assert result.passed()


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


class Test_record_with_argparse:
    def test_ronein_oneout_abspaths(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser
    ):
        parser = sample_argument_parser
        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        output_path = crate_dir / "output.txt"
        input_path.write_text("Hello World\n")
        args = [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        ns = parser.parse_args(args)
        # Simulate the script's main operation
        output_path.write_text(input_path.read_text().upper())
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input"],
                output_files=["output"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["myscript"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        assert crate_meta.exists(), (
            "record() did not produce ro-crate-metadata.json in crate_dir"
        )
        assert_crate_shape(crate_dir)
        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[{"@id": "input.txt"}, {"@id": "output.txt"}],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
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
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"myscript --input {input_path} --output {output_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path} --output {output_path}",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output.txt"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_record_with_argparseonein_oneout_relpaths(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser, monkeypatch
    ):
        parser = sample_argument_parser
        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        output_path = crate_dir / "output.txt"
        input_path.write_text("Hello World\n")

        # Change to crate directory so relative paths resolve correctly
        monkeypatch.chdir(crate_dir)

        args = [
            "--input",
            "input.txt",
            "--output",
            "output.txt",
        ]
        ns = parser.parse_args(args)
        # Simulate the script's main operation
        output_path.write_text(input_path.read_text().upper())
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input"],
                output_files=["output"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["myscript"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[{"@id": "input.txt"}, {"@id": "output.txt"}],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
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
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": "myscript --input input.txt --output output.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input input.txt --output output.txt",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output.txt"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_str_args(self, tmp_path: Path):
        parser = ArgumentParser(prog="myscript", description="Example CLI")
        # Use str types instead of Path
        parser.add_argument("--input", type=str, help="Input file")
        parser.add_argument("--output", type=str, help="Output file")

        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        output_path = crate_dir / "output.txt"
        input_path.write_text("Hello World\n")

        args = [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        ns = parser.parse_args(args)

        # Simulate the script's main operation
        Path(ns.output).write_text(Path(ns.input).read_text().upper())

        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input"],
                output_files=["output"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["myscript"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[{"@id": "input.txt"}, {"@id": "output.txt"}],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
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
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"myscript --input {input_path} --output {output_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path} --output {output_path}",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output.txt"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_filetype_args(self, tmp_path: Path):
        parser = ArgumentParser(prog="myscript", description="Example CLI")
        # Use str types instead of Path
        parser.add_argument("--input", type=FileType("r"), help="Input file")
        parser.add_argument(
            "--output", type=FileType("w", encoding="UTF-8"), help="Output file"
        )

        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"
        output_path = crate_dir / "output.txt"
        input_path.write_text("Hello World\n")

        args = [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        ns = parser.parse_args(args)

        # Simulate the script's main operation
        with ns.input as inp, ns.output as out:
            out.write(inp.read().upper())

        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input"],
                output_files=["output"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["myscript"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[{"@id": "input.txt"}, {"@id": "output.txt"}],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
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
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"myscript --input {input_path} --output {output_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": end_time.isoformat(),
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path} --output {output_path}",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output.txt"}],
                    "startTime": start_time.isoformat(),
                },
            ],
        )

    def test_twice_different_files(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser
    ):
        parser = sample_argument_parser
        crate_dir = tmp_path

        # First run: input.txt -> output.txt
        input1_path = crate_dir / "input.txt"
        output1_path = crate_dir / "output.txt"
        input1_path.write_text("Data 1\n")
        args1 = ["--input", str(input1_path), "--output", str(output1_path)]
        ns1 = parser.parse_args(args1)
        output1_path.write_text(input1_path.read_text().upper())
        start_time1 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        record_with_argparse(
            parser=parser,
            ns=ns1,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time1,
            crate_dir=crate_dir,
            argv=["myscript"] + args1,
            current_user="test_user",
            end_time=end_time1,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        # Second run: input2.txt -> output2.txt
        input2_path = crate_dir / "input2.txt"
        output2_path = crate_dir / "output2.txt"
        input2_path.write_text("Data 2\n")
        args2 = ["--input", str(input2_path), "--output", str(output2_path)]
        ns2 = parser.parse_args(args2)
        output2_path.write_text(input2_path.read_text().upper())
        start_time2 = datetime(2026, 1, 16, 12, 0, 10, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 12, 0, 15, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns2,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time2,
            crate_dir=crate_dir,
            argv=["myscript"] + args2,
            current_user="test_user",
            end_time=end_time2,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        # Cannot use assert_crate_contents here because of the create and update of json file

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
                    "datePublished": "2026-01-16T12:00:15+00:00",
                    "hasPart": [
                        {"@id": "input.txt"},
                        {"@id": "output.txt"},
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
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 7,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {
                    "@id": "output.txt",
                    "@type": "File",
                    "contentSize": 7,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output.txt",
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
                    "description": "Example CLI",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"myscript --input {input1_path} --output {output1_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-16T12:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input1_path} --output {output1_path}",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output.txt"}],
                    "startTime": "2026-01-16T12:00:00+00:00",
                },
                {
                    "@id": "input2.txt",
                    "@type": "File",
                    "contentSize": 7,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input2.txt",
                },
                {
                    "@id": "output2.txt",
                    "@type": "File",
                    "contentSize": 7,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output2.txt",
                },
                {
                    "@id": f"myscript --input {input2_path} --output {output2_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-16T12:00:15+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input2_path} --output {output2_path}",
                    "object": [{"@id": "input2.txt"}],
                    "result": [{"@id": "output2.txt"}],
                    "startTime": "2026-01-16T12:00:10+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_rsame_input_different_output(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser
    ):
        parser = sample_argument_parser
        crate_dir = tmp_path

        input_path = crate_dir / "data.txt"
        input_path.write_text("Shared input\n")

        # First run: process to output1.txt
        output1_path = crate_dir / "output1.txt"
        args1 = ["--input", str(input_path), "--output", str(output1_path)]
        ns1 = parser.parse_args(args1)
        output1_path.write_text(input_path.read_text().upper())
        start_time1 = datetime(2026, 1, 16, 13, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 13, 0, 5, tzinfo=UTC)

        record_with_argparse(
            parser=parser,
            ns=ns1,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time1,
            crate_dir=crate_dir,
            argv=["processor"] + args1,
            current_user="researcher",
            end_time=end_time1,
            software_version="2.0.0",
            dataset_license="CC-BY-4.0",
        )

        output2_path = crate_dir / "output2.txt"
        args2 = ["--input", str(input_path), "--output", str(output2_path)]
        ns2 = parser.parse_args(args2)
        output2_path.write_text(input_path.read_text().lower())
        start_time2 = datetime(2026, 1, 16, 13, 0, 10, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 13, 0, 15, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns2,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time2,
            crate_dir=crate_dir,
            argv=["processor"] + args2,
            current_user="researcher",
            end_time=end_time2,
            software_version="2.0.0",
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
                    "datePublished": "2026-01-16T13:00:15+00:00",
                    "hasPart": [
                        {"@id": "data.txt"},
                        {"@id": "output1.txt"},
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
                    "@id": "data.txt",
                    "@type": "File",
                    "contentSize": 13,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "data.txt",
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
                    "@id": "myscript@2.0.0",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
                    "name": "myscript",
                    "version": "2.0.0",
                },
                {"@id": "researcher", "@type": "Person", "name": "researcher"},
                {
                    "@id": f"processor --input {input_path} --output {output1_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "researcher"},
                    "endTime": "2026-01-16T13:00:05+00:00",
                    "instrument": {"@id": "myscript@2.0.0"},
                    "name": f"processor --input {input_path} --output {output1_path}",
                    "object": [{"@id": "data.txt"}],
                    "result": [{"@id": "output1.txt"}],
                    "startTime": "2026-01-16T13:00:00+00:00",
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
                    "@id": f"processor --input {input_path} --output {output2_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "researcher"},
                    "endTime": "2026-01-16T13:00:15+00:00",
                    "instrument": {"@id": "myscript@2.0.0"},
                    "name": f"processor --input {input_path} --output {output2_path}",
                    "object": [{"@id": "data.txt"}],
                    "result": [{"@id": "output2.txt"}],
                    "startTime": "2026-01-16T13:00:10+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_rsame_command_twice(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser
    ):
        parser = sample_argument_parser
        crate_dir = tmp_path

        input_path = crate_dir / "input.txt"
        output_path = crate_dir / "output.txt"
        input_path.write_text("Test\n")

        # First invocation
        args = ["--input", str(input_path), "--output", str(output_path)]
        ns = parser.parse_args(args)
        output_path.write_text(input_path.read_text())
        start_time1 = datetime(2026, 1, 16, 14, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 16, 14, 0, 5, tzinfo=UTC)

        record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time1,
            crate_dir=crate_dir,
            argv=["process"] + args,
            current_user="bot",
            end_time=end_time1,
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

        # Second invocation - identical command
        ns2 = parser.parse_args(args)
        output_path.write_text(input_path.read_text())
        start_time2 = datetime(2026, 1, 16, 14, 0, 10, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 16, 14, 0, 15, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns2,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time2,
            crate_dir=crate_dir,
            argv=["process"] + args,
            current_user="bot",
            end_time=end_time2,
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
        expected_entities = {
                       "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                "https://w3id.org/ro/terms/workflow-run/context",
            ], "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "datePublished": "2026-01-16T14:00:15+00:00",
                    "hasPart": [{"@id": "input.txt"}, {"@id": "output.txt"}],
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
                    "@id": "input.txt",
                    "@type": "File",
                    "contentSize": 5,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "input.txt",
                },
                {
                    "@id": "output.txt",
                    "@type": "File",
                    "contentSize": 5,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "output.txt",
                },
                                {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    "@type": "CreativeWork",
                    "name": "Process Run Crate",
                    "version": "0.5",
                },
                {
                    "@id": "myscript@1.0.0",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
                    "name": "myscript",
                    "version": "1.0.0",
                },
                {"@id": "bot", "@type": "Person", "name": "bot"},
                {
                    "@id": f"process --input {input_path} --output {output_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "bot"},
                    "endTime": "2026-01-16T14:00:05+00:00",
                    "instrument": {"@id": "myscript@1.0.0"},
                    "name": f"process --input {input_path} --output {output_path}",
                    "object": [{"@id": "input.txt"}],
                    "result": [{"@id": "output.txt"}],
                    "startTime": "2026-01-16T14:00:00+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_rtwo_different_commands(self, tmp_path: Path):
        """Test recording actions from two different software applications.

        Should result in 2 distinct SoftwareApplication entities in the RO-Crate.
        """
        crate_dir = tmp_path

        # First command: converter
        parser1 = ArgumentParser(prog="converter", description="Convert files")
        parser1.add_argument("--input", type=Path, help="Input file")
        parser1.add_argument("--output", type=Path, help="Output file")

        input1_path = crate_dir / "data.txt"
        output1_path = crate_dir / "converted.txt"
        input1_path.write_text("original\n")

        args1 = ["--input", str(input1_path), "--output", str(output1_path)]
        ns1 = parser1.parse_args(args1)
        output1_path.write_text(input1_path.read_text().upper())

        start_time1 = datetime(2026, 1, 17, 10, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 17, 10, 0, 5, tzinfo=UTC)

        record_with_argparse(
            parser=parser1,
            ns=ns1,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time1,
            crate_dir=crate_dir,
            argv=["converter"] + args1,
            current_user="researcher",
            end_time=end_time1,
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

        # Second command: analyzer (different program)
        parser2 = ArgumentParser(prog="analyzer", description="Analyze files")
        parser2.add_argument("--input", type=Path, help="File to analyze")
        parser2.add_argument("--output", type=Path, help="Analysis result")

        input2_path = crate_dir / "converted.txt"
        output2_path = crate_dir / "analysis.json"

        args2 = ["--input", str(input2_path), "--output", str(output2_path)]
        ns2 = parser2.parse_args(args2)
        output2_path.write_text('{"count": 8}\n')

        start_time2 = datetime(2026, 1, 17, 10, 0, 10, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 17, 10, 0, 15, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser2,
            ns=ns2,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time2,
            crate_dir=crate_dir,
            argv=["analyzer"] + args2,
            current_user="researcher",
            end_time=end_time2,
            software_version="2.5.0",
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
        expected_entities = {
                      "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                "https://w3id.org/ro/terms/workflow-run/context",
            ],  "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "datePublished": "2026-01-17T10:00:15+00:00",
                    "hasPart": [
                        {"@id": "data.txt"},
                        {"@id": "converted.txt"},
                        {"@id": "analysis.json"},
                    ],
                    "license": "CC-BY-4.0",
                                   "conformsTo": {
                        "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    },
                    "name": "Files used by converter",
                    "description": "An RO-Crate recording the files and directories that were used as input or output by converter.",
                },
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"},
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                },
                {
                    "@id": "data.txt",
                    "@type": "File",
                    "contentSize": 9,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "data.txt",
                },
                {
                    "@id": "converted.txt",
                    "@type": "File",
                    "contentSize": 9,
                    "description": "File to analyze",
                    "encodingFormat": "text/plain",
                    "name": "converted.txt",
                },
                                {
                    "@id": "https://w3id.org/ro/wfrun/process/0.5",
                    "@type": "CreativeWork",
                    "name": "Process Run Crate",
                    "version": "0.5",
                },
                {
                    "@id": "converter@1.0.0",
                    "@type": "SoftwareApplication",
                    "description": "Convert files",
                    "name": "converter",
                    "version": "1.0.0",
                },
                {"@id": "researcher", "@type": "Person", "name": "researcher"},
                {
                    "@id": f"converter --input {input1_path} --output {output1_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "researcher"},
                    "endTime": "2026-01-17T10:00:05+00:00",
                    "instrument": {"@id": "converter@1.0.0"},
                    "name": f"converter --input {input1_path} --output {output1_path}",
                    "object": [{"@id": "data.txt"}],
                    "result": [{"@id": "converted.txt"}],
                    "startTime": "2026-01-17T10:00:00+00:00",
                },
                {
                    "@id": "analyzer@2.5.0",
                    "@type": "SoftwareApplication",
                    "description": "Analyze files",
                    "name": "analyzer",
                    "version": "2.5.0",
                },
                {
                    "@id": "analysis.json",
                    "@type": "File",
                    "contentSize": 13,
                    "description": "Analysis result",
                    "encodingFormat": "application/json",
                    "name": "analysis.json",
                },
                {
                    "@id": f"analyzer --input {input2_path} --output {output2_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "researcher"},
                    "endTime": "2026-01-17T10:00:15+00:00",
                    "instrument": {"@id": "analyzer@2.5.0"},
                    "name": f"analyzer --input {input2_path} --output {output2_path}",
                    "object": [{"@id": "converted.txt"}],
                    "result": [{"@id": "analysis.json"}],
                    "startTime": "2026-01-17T10:00:10+00:00",
                },
            ],
        }
        assert actual_entities == expected_entities

    def test_rdirs(self, tmp_path: Path):
        """Test recording with --input-dir and --output-dir arguments.

        Simulates copying files from input dir to output dir with uppercased filenames and contents.
        """
        parser = ArgumentParser(prog="dirprocessor", description="Process directories")
        parser.add_argument("--input-dir", type=Path, help="Input directory")
        parser.add_argument("--output-dir", type=Path, help="Output directory")

        crate_dir = tmp_path
        input_dir = crate_dir / "input"
        output_dir = crate_dir / "output"

        # Create input directory with some files
        input_dir.mkdir()
        (input_dir / "file1.txt").write_text("hello world\n")
        (input_dir / "file2.txt").write_text("foo bar\n")

        # Create output directory
        output_dir.mkdir()

        args = [
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
        ]
        ns = parser.parse_args(args)

        # Simulate the script's main operation: copy files with uppercased names and contents
        for file_path in input_dir.iterdir():
            if file_path.is_file():
                uppercase_name = file_path.name.upper()
                uppercase_content = file_path.read_text().upper()
                (output_dir / uppercase_name).write_text(uppercase_content)

        start_time = datetime(2026, 1, 17, 13, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 17, 13, 0, 10, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_dirs=["input_dir"],
                output_dirs=["output_dir"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["dirprocessor"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="dirprocessor",
            end_time=end_time,
            has_part=[{"@id": "input/"}, {"@id": "output/"}],
            custom_entities=[
                {
                    "@id": "dirprocessor@1.0.0",
                    "@type": "SoftwareApplication",
                    "description": "Process directories",
                    "name": "dirprocessor",
                    "version": "1.0.0",
                },
                {"@id": "input/", "@type": "Dataset", "name": "input"},
                {"@id": "output/", "@type": "Dataset", "name": "output"},
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"dirprocessor --input-dir {input_dir} --output-dir {output_dir}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-17T13:00:10+00:00",
                    "instrument": {"@id": "dirprocessor@1.0.0"},
                    "name": f"dirprocessor --input-dir {input_dir} --output-dir {output_dir}",
                    "object": [{"@id": "input/"}],
                    "result": [{"@id": "output/"}],
                    "startTime": "2026-01-17T13:00:00+00:00",
                },
            ],
        )

    def test_rfiles_in_single_level_subdirectories(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser
    ):
        """Test recording with files in single-level subdirectories using absolute paths."""
        parser = sample_argument_parser
        crate_dir = tmp_path

        # Create subdirectories
        input_dir = crate_dir / "data"
        input_dir.mkdir()
        output_dir = crate_dir / "results"
        output_dir.mkdir()

        # Create input file in subdirectory
        input_path = input_dir / "input.txt"
        input_path.write_text("Hello from subdirectory\n")

        # Define output path in subdirectory
        output_path = output_dir / "output.txt"

        args = [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        ns = parser.parse_args(args)

        # Simulate the script's main operation
        output_path.write_text(input_path.read_text().upper())

        start_time = datetime(2026, 1, 18, 10, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 18, 10, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input"],
                output_files=["output"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["myscript"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[{"@id": "data/input.txt"}, {"@id": "results/output.txt"}],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "data/input.txt",
                    "@type": "File",
                    "contentSize": 24,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "data/input.txt",
                },
                {
                    "@id": "results/output.txt",
                    "@type": "File",
                    "contentSize": 24,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "results/output.txt",
                },
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"myscript --input {input_path} --output {output_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-18T10:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path} --output {output_path}",
                    "object": [{"@id": "data/input.txt"}],
                    "result": [{"@id": "results/output.txt"}],
                    "startTime": "2026-01-18T10:00:00+00:00",
                },
            ],
        )

    def test_rfiles_in_single_level_subdirectories_relpaths(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser, monkeypatch
    ):
        """Test recording with files in single-level subdirectories using relative paths."""
        parser = sample_argument_parser
        crate_dir = tmp_path

        # Create subdirectories
        input_dir = crate_dir / "data"
        input_dir.mkdir()
        output_dir = crate_dir / "results"
        output_dir.mkdir()

        # Create input file in subdirectory
        input_path = input_dir / "input.txt"
        input_path.write_text("Hello from subdirectory\n")

        # Define output path in subdirectory
        output_path = output_dir / "output.txt"

        # Change to crate directory so relative paths resolve correctly
        monkeypatch.chdir(crate_dir)

        args = [
            "--input",
            "data/input.txt",
            "--output",
            "results/output.txt",
        ]
        ns = parser.parse_args(args)

        # Simulate the script's main operation
        output_path.write_text(input_path.read_text().upper())

        start_time = datetime(2026, 1, 18, 10, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 18, 10, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input"],
                output_files=["output"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["myscript"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[
                {"@id": "data/input.txt"},
                {"@id": "results/output.txt"},
            ],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "data/input.txt",
                    "@type": "File",
                    "contentSize": 24,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "data/input.txt",
                },
                {
                    "@id": "results/output.txt",
                    "@type": "File",
                    "contentSize": 24,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "results/output.txt",
                },
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": "myscript --input data/input.txt --output results/output.txt",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-18T10:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": "myscript --input data/input.txt --output results/output.txt",
                    "object": [{"@id": "data/input.txt"}],
                    "result": [{"@id": "results/output.txt"}],
                    "startTime": "2026-01-18T10:00:00+00:00",
                },
            ],
        )

    def test_rfiles_in_nested_subdirectories(
        self, tmp_path: Path, sample_argument_parser: ArgumentParser
    ):
        """Test recording with files in nested subdirectories using absolute paths."""
        parser = sample_argument_parser
        crate_dir = tmp_path

        # Create nested subdirectories
        input_dir = crate_dir / "data" / "nested"
        input_dir.mkdir(parents=True)
        output_dir = crate_dir / "results" / "processed"
        output_dir.mkdir(parents=True)

        # Create input file in nested subdirectory
        input_path = input_dir / "input.txt"
        input_path.write_text("Nested data\n")

        # Define output path in nested subdirectory
        output_path = output_dir / "output.txt"

        args = [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        ns = parser.parse_args(args)

        # Simulate the script's main operation
        output_path.write_text(input_path.read_text().upper())

        start_time = datetime(2026, 1, 18, 11, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 18, 11, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input"],
                output_files=["output"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["myscript"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.2.3",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            has_part=[
                {"@id": "data/nested/input.txt"},
                {"@id": "results/processed/output.txt"},
            ],
            custom_entities=[
                {
                    "@id": "myscript@1.2.3",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
                    "name": "myscript",
                    "version": "1.2.3",
                },
                {
                    "@id": "data/nested/input.txt",
                    "@type": "File",
                    "contentSize": 12,
                    "description": "Input file",
                    "encodingFormat": "text/plain",
                    "name": "data/nested/input.txt",
                },
                {
                    "@id": "results/processed/output.txt",
                    "@type": "File",
                    "contentSize": 12,
                    "description": "Output file",
                    "encodingFormat": "text/plain",
                    "name": "results/processed/output.txt",
                },
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"myscript --input {input_path} --output {output_path}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-18T11:00:05+00:00",
                    "instrument": {"@id": "myscript@1.2.3"},
                    "name": f"myscript --input {input_path} --output {output_path}",
                    "object": [{"@id": "data/nested/input.txt"}],
                    "result": [{"@id": "results/processed/output.txt"}],
                    "startTime": "2026-01-18T11:00:00+00:00",
                },
            ],
        )

    def test_rnesteddirs(self, tmp_path: Path):
        """Test recording with nested directories in --input-dir and --output-dir arguments.

        Simulates copying files from nested input dir to nested output dir with uppercased content.
        """
        parser = ArgumentParser(prog="dirprocessor", description="Process directories")
        parser.add_argument("--input-dir", type=Path, help="Input directory")
        parser.add_argument("--output-dir", type=Path, help="Output directory")

        crate_dir = tmp_path
        input_dir = crate_dir / "input" / "nested"
        output_dir = crate_dir / "output" / "processed"

        # Create nested input directory with some files
        input_dir.mkdir(parents=True)
        (input_dir / "file1.txt").write_text("hello world\n")
        (input_dir / "file2.txt").write_text("foo bar\n")

        # Create nested output directory
        output_dir.mkdir(parents=True)

        args = [
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
        ]
        ns = parser.parse_args(args)

        # Simulate the script's main operation: copy files with uppercased names and contents
        for file_path in input_dir.iterdir():
            if file_path.is_file():
                uppercase_name = file_path.name.upper()
                uppercase_content = file_path.read_text().upper()
                (output_dir / uppercase_name).write_text(uppercase_content)

        start_time = datetime(2026, 1, 18, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 18, 12, 0, 10, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_dirs=["input_dir"],
                output_dirs=["output_dir"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["dirprocessor"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="dirprocessor",
            end_time=end_time,
            has_part=[{"@id": "input/nested/"}, {"@id": "output/processed/"}],
            custom_entities=[
                {
                    "@id": "dirprocessor@1.0.0",
                    "@type": "SoftwareApplication",
                    "description": "Process directories",
                    "name": "dirprocessor",
                    "version": "1.0.0",
                },
                {"@id": "input/nested/", "@type": "Dataset", "name": "input/nested"},
                {
                    "@id": "output/processed/",
                    "@type": "Dataset",
                    "name": "output/processed",
                },
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"dirprocessor --input-dir {input_dir} --output-dir {output_dir}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-18T12:00:10+00:00",
                    "instrument": {"@id": "dirprocessor@1.0.0"},
                    "name": f"dirprocessor --input-dir {input_dir} --output-dir {output_dir}",
                    "object": [{"@id": "input/nested/"}],
                    "result": [{"@id": "output/processed/"}],
                    "startTime": "2026-01-18T12:00:00+00:00",
                },
            ],
        )

    def test_rsubcommand_multiple_different(self, tmp_path: Path):
        """Test recording multiple different subcommands in the same crate."""
        parser = ArgumentParser(prog="git", description="Git version control system")
        subparsers = parser.add_subparsers(dest="command", help="Git commands")

        # Add 'commit' subcommand
        commit_parser = subparsers.add_parser("commit", help="Record changes")
        commit_parser.add_argument("--input", type=Path, help="File to commit")
        commit_parser.add_argument("--output", type=Path, help="Commit log")

        # Add 'push' subcommand
        push_parser = subparsers.add_parser("push", help="Upload changes")
        push_parser.add_argument("--input", type=Path, help="Local repository")
        push_parser.add_argument("--output", type=Path, help="Remote repository")

        crate_dir = tmp_path

        # First action: git commit
        commit_input = crate_dir / "changes.txt"
        commit_output = crate_dir / "commit_log.txt"
        commit_input.write_text("Feature A\n")

        args1 = ["commit", "--input", str(commit_input), "--output", str(commit_output)]
        ns1 = parser.parse_args(args1)
        commit_output.write_text(f"Committed: {commit_input.read_text()}")

        start_time1 = datetime(2026, 1, 18, 17, 0, 0, tzinfo=UTC)
        end_time1 = datetime(2026, 1, 18, 17, 0, 5, tzinfo=UTC)

        record_with_argparse(
            parser=parser,
            ns=ns1,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time1,
            crate_dir=crate_dir,
            argv=["git"] + args1,
            current_user="developer",
            end_time=end_time1,
            software_version="2.40.0",
            dataset_license="CC-BY-4.0",
        )

        # Second action: git push
        push_input = crate_dir / "local_repo.txt"
        push_output = crate_dir / "remote_repo.txt"
        push_input.write_text("Local commits\n")

        args2 = ["push", "--input", str(push_input), "--output", str(push_output)]
        ns2 = parser.parse_args(args2)
        push_output.write_text(f"Pushed: {push_input.read_text()}")

        start_time2 = datetime(2026, 1, 18, 17, 0, 10, tzinfo=UTC)
        end_time2 = datetime(2026, 1, 18, 17, 0, 15, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns2,
            ios=IOs(input_files=["input"], output_files=["output"]),
            start_time=start_time2,
            crate_dir=crate_dir,
            argv=["git"] + args2,
            current_user="developer",
            end_time=end_time2,
            software_version="2.40.0",
            dataset_license="CC-BY-4.0",
        )

        actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))

        # Verify single SoftwareApplication entity for "git"
        software_apps = [
            e
            for e in actual_entities["@graph"]
            if e.get("@type") == "SoftwareApplication"
        ]
        assert len(software_apps) == 1
        assert software_apps[0]["@id"] == "git@2.40.0"
        assert software_apps[0]["name"] == "git"

        # Verify two CreateAction entities with different command lines
        create_actions = [
            e for e in actual_entities["@graph"] if e.get("@type") == "CreateAction"
        ]
        assert len(create_actions) == 2

        action_names = {a["name"] for a in create_actions}
        assert (
            f"git commit --input {commit_input} --output {commit_output}"
            in action_names
        )
        assert f"git push --input {push_input} --output {push_output}" in action_names

        # Both actions should reference the same instrument
        for action in create_actions:
            assert action["instrument"]["@id"] == "git@2.40.0"

    def test_multiple_args_same_file(self, tmp_path: Path):
        """Verifies that when the same file is referenced by different arguments
        (--input and --ref both pointing to file1.txt), the crate is created correctly
        with the file appearing only once in the object array.
        """
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--input", type=Path, help="Input file")
        parser.add_argument("--ref", type=Path, help="Reference file")

        crate_dir = tmp_path
        shared_file = crate_dir / "file1.txt"
        shared_file.write_text("Shared content\n")

        args = ["--input", str(shared_file), "--ref", str(shared_file)]
        ns = parser.parse_args(args)

        start_time = datetime(2026, 1, 19, 10, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 19, 10, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(
                input_files=["input", "ref"],
            ),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=["processor"] + args,
            current_user="test_user",
            end_time=end_time,
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="processor",
            end_time=end_time,
            has_part=[{"@id": "file1.txt"}],
            custom_entities=[
                {
                    "@id": "processor@1.0.0",
                    "@type": "SoftwareApplication",
                    "description": "Process files",
                    "name": "processor",
                    "version": "1.0.0",
                },
                {
                    "@id": "file1.txt",
                    "@type": "File",
                    "contentSize": 15,
                    "description": "Reference file",
                    "encodingFormat": "text/plain",
                    "name": "file1.txt",
                },
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": f"processor --input {shared_file} --ref {shared_file}",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-19T10:00:05+00:00",
                    "instrument": {"@id": "processor@1.0.0"},
                    "name": f"processor --input {shared_file} --ref {shared_file}",
                    "object": [{"@id": "file1.txt"}],
                    "startTime": "2026-01-19T10:00:00+00:00",
                },
            ],
        )

    def test_version_from_parser(self, tmp_path: Path):
        crate_dir = tmp_path
        prog = "myscript"
        parser = ArgumentParser(prog=prog, description="Example CLI")
        parser.add_argument("--version", action="version", version="myscript 3.2.1")
        args = []
        ns = parser.parse_args(args)

        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 16, 12, 0, 5, tzinfo=UTC)

        crate_meta = record_with_argparse(
            parser=parser,
            ns=ns,
            ios=IOs(),
            start_time=start_time,
            crate_dir=crate_dir,
            argv=[prog] + args,
            current_user="test_user",
            end_time=end_time,
            dataset_license="CC-BY-4.0",
        )

        assert_crate_contents(
            crate_meta=crate_meta,
            program_name="myscript",
            end_time=end_time,
            custom_entities=[
                {
                    "@id": "myscript@3.2.1",
                    "@type": "SoftwareApplication",
                    "description": "Example CLI",
                    "name": "myscript",
                    "version": "3.2.1",
                },
                {"@id": "test_user", "@type": "Person", "name": "test_user"},
                {
                    "@id": "myscript",
                    "@type": "CreateAction",
                    "agent": {"@id": "test_user"},
                    "endTime": "2026-01-16T12:00:05+00:00",
                    "instrument": {"@id": "myscript@3.2.1"},
                    "name": "myscript",
                    "startTime": "2026-01-16T12:00:00+00:00",
                },
            ],
        )


def test_argparse_value2paths_stdin_handling():
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", type=argparse.FileType("r"))
    args = parser.parse_args(["-"])

    result = argparse_value2paths(args.infile)

    assert result == [], "Expected empty list for stdin file argument"
    # Unable to test FileType('w') for stdout due to reading .name
    # causes `alueError: I/O operation on closed file.` while in pytest


class Test_argparse_info:
    def test_subcommand_single_level(self, tmp_path: Path):
        """Test argparse_info extracts single-level subcommand (e.g., git commit)."""
        # Create main parser with subcommands
        parser = ArgumentParser(prog="git", description="Git version control system")
        subparsers = parser.add_subparsers(dest="command", help="Git commands")

        # Add 'commit' subcommand
        commit_parser = subparsers.add_parser(
            "commit", help="Record changes to repository"
        )
        commit_parser.add_argument("--input", type=Path, help="File to commit")
        commit_parser.add_argument("--output", type=Path, help="Commit log file")

        input_path = tmp_path / "changes.txt"
        output_path = tmp_path / "commit_log.txt"
        args = ["commit", "--input", str(input_path), "--output", str(output_path)]
        ns = parser.parse_args(args)

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="git",
                description="Git version control system",
                subcommands={"commit": Program(name="git commit", description="")},
            ),
            ioarguments={
                "command": [IOArgument(name="command", path=Path("commit"), help="")],
                "input": [
                    IOArgument(name="input", path=input_path, help="File to commit")
                ],
                "output": [
                    IOArgument(name="output", path=output_path, help="Commit log file")
                ],
            },
        )
        assert info == expected

    def test_subcommand_nested_levels(self, tmp_path: Path):
        """Test argparse_info extracts nested subcommands (e.g., git remote add)."""
        # Create main parser
        parser = ArgumentParser(prog="git", description="Git version control system")
        subparsers = parser.add_subparsers(dest="command", help="Git commands")

        # Add 'remote' subcommand with its own subcommands
        remote_parser = subparsers.add_parser(
            "remote", help="Manage remote repositories"
        )
        remote_subparsers = remote_parser.add_subparsers(
            dest="action", help="Remote actions"
        )

        # Add 'add' subcommand under 'remote'
        add_parser = remote_subparsers.add_parser("add", help="Add a new remote")
        add_parser.add_argument("--input", type=Path, help="Config file")
        add_parser.add_argument("--output", type=Path, help="Updated config")

        input_path = tmp_path / "git_config.txt"
        output_path = tmp_path / "git_config_updated.txt"
        args = [
            "remote",
            "add",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        ns = parser.parse_args(args)

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="git",
                description="Git version control system",
                subcommands={
                    "remote": Program(
                        name="git remote",
                        description="",
                        subcommands={
                            "add": Program(name="git remote add", description="")
                        },
                    )
                },
            ),
            ioarguments={
                "command": [IOArgument(name="command", path=Path("remote"), help="")],
                "action": [IOArgument(name="action", path=Path("add"), help="")],
                "input": [
                    IOArgument(name="input", path=input_path, help="Config file")
                ],
                "output": [
                    IOArgument(name="output", path=output_path, help="Updated config")
                ],
            },
        )
        assert info == expected

    def test_subcommand_missing_dest(self, tmp_path: Path):
        """Test that missing dest parameter in add_subparsers raises ValueError."""
        parser = ArgumentParser(prog="tool", description="A tool")
        subparsers = parser.add_subparsers(help="Commands")  # Missing dest parameter

        action_parser = subparsers.add_parser("action", help="Do something")
        action_parser.add_argument("--input", type=Path, help="Input file")

        input_path = tmp_path / "input.txt"
        args = ["action", "--input", str(input_path)]
        ns = parser.parse_args(args)

        with pytest.raises(
            ValueError,
            match=r"record_with_argparse requires add_subparsers\(dest='name'\) with dest parameter set",
        ):
            argparse_info(ns, parser)

    def test_subcommand_with_parent_flags(self, tmp_path: Path):
        """Test argparse_info handles flags before subcommand (e.g., git --no-pager status)."""
        # Create main parser with global flags
        parser = ArgumentParser(prog="git", description="Git version control system")
        parser.add_argument(
            "--no-pager", action="store_true", help="Do not pipe output into a pager"
        )
        subparsers = parser.add_subparsers(dest="command", help="Git commands")

        # Add 'status' subcommand
        status_parser = subparsers.add_parser("status", help="Show working tree status")
        status_parser.add_argument("--input", type=Path, help="Repository directory")
        status_parser.add_argument("--output", type=Path, help="Status output file")

        input_path = tmp_path / "repo"
        output_path = tmp_path / "status.txt"
        args = [
            "--no-pager",
            "status",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        ns = parser.parse_args(args)

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="git",
                description="Git version control system",
                subcommands={"status": Program(name="git status", description="")},
            ),
            ioarguments={
                "command": [IOArgument(name="command", path=Path("status"), help="")],
                "input": [
                    IOArgument(
                        name="input", path=input_path, help="Repository directory"
                    )
                ],
                "output": [
                    IOArgument(
                        name="output", path=output_path, help="Status output file"
                    )
                ],
            },
        )
        assert info == expected

    def test_nargs_star_empty(self):
        """Test argparse_info with nargs='*' and no values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        ns = parser.parse_args([])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={},
        )
        assert info == expected

    def test_nargs_star_single(self):
        """Test argparse_info with nargs='*' and single value provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        input_file = Path("input.txt")
        ns = parser.parse_args(["--inputs", str(input_file)])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(name="inputs", path=input_file, help="Input files")
                ]
            },
        )
        assert info == expected

    def test_nargs_star_multiple(self):
        """Test argparse_info with nargs='*' and multiple values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(name="inputs", path=input_files[0], help="Input files"),
                    IOArgument(name="inputs", path=input_files[1], help="Input files"),
                    IOArgument(name="inputs", path=input_files[2], help="Input files"),
                ]
            },
        )
        assert info == expected

    def test_action_append_multiple(self):
        """Test argparse_info with action='append' and multiple values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", action="append", type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(
            [
                "--inputs",
                str(input_files[0]),
                "--inputs",
                str(input_files[1]),
                "--inputs",
                str(input_files[2]),
            ]
        )

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(name="inputs", path=input_files[0], help="Input files"),
                    IOArgument(name="inputs", path=input_files[1], help="Input files"),
                    IOArgument(name="inputs", path=input_files[2], help="Input files"),
                ]
            },
        )
        assert info == expected

    def test_action_extend_multiple(self):
        """Test argparse_info with action='extend' and multiple values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument(
            "--inputs", action="extend", nargs="+", type=Path, help="Input files"
        )
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(
            [
                "--inputs",
                str(input_files[0]),
                str(input_files[1]),
                "--inputs",
                str(input_files[2]),
            ]
        )

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(name="inputs", path=input_files[0], help="Input files"),
                    IOArgument(name="inputs", path=input_files[1], help="Input files"),
                    IOArgument(name="inputs", path=input_files[2], help="Input files"),
                ]
            },
        )
        assert info == expected

    def test_nargs_star_with_duplicates(self):
        """Test argparse_info with nargs='*' and duplicate paths provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file1.txt"), Path("file2.txt")]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(
                        name="inputs", path=Path("file1.txt"), help="Input files"
                    ),
                    IOArgument(
                        name="inputs", path=Path("file2.txt"), help="Input files"
                    ),
                ]
            },
        )
        assert info == expected

    def test_nargs_plus_single(self):
        """Test argparse_info with nargs='+' and single value provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="+", type=Path, help="Input files")
        input_file = Path("input.txt")
        ns = parser.parse_args(["--inputs", str(input_file)])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(name="inputs", path=input_file, help="Input files")
                ]
            },
        )
        assert info == expected

    def test_nargs_plus_multiple(self):
        """Test argparse_info with nargs='+' and multiple values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="+", type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(name="inputs", path=input_files[0], help="Input files"),
                    IOArgument(name="inputs", path=input_files[1], help="Input files"),
                    IOArgument(name="inputs", path=input_files[2], help="Input files"),
                ]
            },
        )
        assert info == expected

    def test_nargs_int(self):
        """Test argparse_info with nargs=2 (specific count)."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs=2, type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt")]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "inputs": [
                    IOArgument(name="inputs", path=input_files[0], help="Input files"),
                    IOArgument(name="inputs", path=input_files[1], help="Input files"),
                ]
            },
        )
        assert info == expected

    def test_nargs_question_with_value(self):
        """Test argparse_info with nargs='?' and value provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--input", nargs="?", type=Path, help="Input file")
        input_file = Path("input.txt")
        ns = parser.parse_args(["--input", str(input_file)])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={
                "input": [IOArgument(name="input", path=input_file, help="Input file")]
            },
        )
        assert info == expected

    def test_nargs_question_without_value(self):
        """Test argparse_info with nargs='?' and no value provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--input", nargs="?", type=Path, help="Input file")
        ns = parser.parse_args([])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="processor",
                description="Process files",
            ),
            ioarguments={},
        )
        assert info == expected

    def test_positional_args(self):
        """Test argparse_info with positional arguments (input.txt output.txt)."""
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("input", type=Path, help="Input file")
        parser.add_argument("output", type=Path, help="Output file")

        input_file = Path("input.txt")
        output_file = Path("output.txt")
        ns = parser.parse_args([str(input_file), str(output_file)])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="myscript",
                description="Process input and generate output",
            ),
            ioarguments={
                "input": [IOArgument(name="input", path=input_file, help="Input file")],
                "output": [
                    IOArgument(name="output", path=output_file, help="Output file")
                ],
            },
        )
        assert info == expected

    def test_arg_with_default(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument(
            "--input", type=Path, default=Path("input.txt"), help="Input file"
        )

        # Don't provide input, it will use default
        ns = parser.parse_args([])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="myscript",
                description="Process input and generate output",
            ),
            ioarguments={
                "input": [
                    IOArgument(name="input", path=Path("input.txt"), help="Input file")
                ],
            },
        )
        assert info == expected

    def test_args_with_dest(self):
        """Test argparse_info with arguments using custom dest names."""
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--input", dest="myinput", type=Path, help="Input file")
        parser.add_argument("--output", dest="myoutput", type=Path, help="Output file")

        input_file = Path("input.txt")
        output_file = Path("output.txt")
        ns = parser.parse_args(
            ["--input", str(input_file), "--output", str(output_file)]
        )

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="myscript",
                description="Process input and generate output",
            ),
            ioarguments={
                "myinput": [
                    IOArgument(name="myinput", path=input_file, help="Input file")
                ],
                "myoutput": [
                    IOArgument(name="myoutput", path=output_file, help="Output file")
                ],
            },
        )
        assert info == expected

    def test_args_with_flags(self):
        """Test argparse_info with arguments using short and long flags."""
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("-i", "--input", type=Path, help="Input file")

        input_file = Path("input.txt")
        ns = parser.parse_args(["-i", str(input_file)])

        info = argparse_info(ns, parser)

        expected = Info(
            program=Program(
                name="myscript",
                description="Process input and generate output",
            ),
            ioarguments={
                "input": [IOArgument(name="input", path=input_file, help="Input file")],
            },
        )
        assert info == expected


class Test_version_from_parser:
    def test_golden_path(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--version", action="version", version="%(prog)s 2.0.1")

        version = version_from_parser(parser)

        assert version == "2.0.1"

    def test_bare_version(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--version", action="version", version="1.2.3")

        version = version_from_parser(parser)

        assert version == "1.2.3"

    def test_no_version(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--input", type=Path, help="Input file")
        # No version argument added

        version = version_from_parser(parser)

        assert version is None
