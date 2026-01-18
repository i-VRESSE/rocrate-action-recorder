from argparse import ArgumentParser, FileType
import argparse
import json
from pathlib import Path
from datetime import UTC, datetime

import pytest
from rocrate_validator import services, models
from rocrate_validator.utils.uri import URI

from rocrate_action_recorder import record_with_argparse, IOs
from rocrate_action_recorder.adapters.argparse import argparse_value2path


@pytest.fixture
def sample_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="myscript", description="Example CLI")
    parser.add_argument("--input", type=Path, help="Input file")
    parser.add_argument("--output", type=Path, help="Output file")
    return parser


def assert_crate_shape(crate_dir: Path) -> None:
    settings = models.ValidationSettings(
        rocrate_uri=URI(crate_dir),
        # TODO use more comprehensive provenance-run-crate profile
        profile_identifier="process-run-crate",
        requirement_severity=models.Severity.RECOMMENDED,
    )
    result = services.validate(settings)
    assert result.passed()


def test_onein_oneout_abspaths(tmp_path: Path, sample_argument_parser: ArgumentParser):
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
    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-16T12:00:05+00:00",
                "hasPart": [{"@id": "input.txt"}, {"@id": "output.txt"}],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
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
                "endTime": "2026-01-16T12:00:05+00:00",
                "instrument": {"@id": "myscript@1.2.3"},
                "name": f"myscript --input {input_path} --output {output_path}",
                "object": [{"@id": "input.txt"}],
                "result": [{"@id": "output.txt"}],
                "startTime": "2026-01-16T12:00:00+00:00",
            },
        ],
    }
    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    assert actual_entities == expected_entities


def test_strargs(tmp_path: Path) -> None:
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

    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-16T12:00:05+00:00",
                "hasPart": [{"@id": "input.txt"}, {"@id": "output.txt"}],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
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
                "endTime": "2026-01-16T12:00:05+00:00",
                "instrument": {"@id": "myscript@1.2.3"},
                "name": f"myscript --input {input_path} --output {output_path}",
                "object": [{"@id": "input.txt"}],
                "result": [{"@id": "output.txt"}],
                "startTime": "2026-01-16T12:00:00+00:00",
            },
        ],
    }
    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    assert actual_entities == expected_entities


def test_filetypeargs(tmp_path: Path) -> None:
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

    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-16T12:00:05+00:00",
                "hasPart": [{"@id": "input.txt"}, {"@id": "output.txt"}],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
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
                "endTime": "2026-01-16T12:00:05+00:00",
                "instrument": {"@id": "myscript@1.2.3"},
                "name": f"myscript --input {input_path} --output {output_path}",
                "object": [{"@id": "input.txt"}],
                "result": [{"@id": "output.txt"}],
                "startTime": "2026-01-16T12:00:00+00:00",
            },
        ],
    }
    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    assert actual_entities == expected_entities


def test_record_different_files(tmp_path: Path, sample_argument_parser: ArgumentParser):
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

    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
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


def test_record_same_input_different_output(
    tmp_path: Path, sample_argument_parser: ArgumentParser
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

    # Second run: same input, process to output2.txt
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
        "@context": "https://w3id.org/ro/crate/1.1/context",
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


def test_record_same_command_twice(
    tmp_path: Path, sample_argument_parser: ArgumentParser
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
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-16T14:00:15+00:00",
                "hasPart": [{"@id": "input.txt"}, {"@id": "output.txt"}],
                "license": "CC-BY-4.0",
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


def test_record_two_different_commands(tmp_path: Path):
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
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
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


def test_dirs(tmp_path: Path) -> None:
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

    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-17T13:00:10+00:00",
                "hasPart": [{"@id": "input/"}, {"@id": "output/"}],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
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
    }
    assert actual_entities == expected_entities


def test_files_in_single_level_subdirectories(
    tmp_path: Path, sample_argument_parser: ArgumentParser
) -> None:
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

    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-18T10:00:05+00:00",
                "hasPart": [{"@id": "data/input.txt"}, {"@id": "results/output.txt"}],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
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
    }
    assert actual_entities == expected_entities


def test_files_in_nested_subdirectories(
    tmp_path: Path, sample_argument_parser: ArgumentParser
) -> None:
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

    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-18T11:00:05+00:00",
                "hasPart": [
                    {"@id": "data/nested/input.txt"},
                    {"@id": "results/processed/output.txt"},
                ],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
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
    }
    assert actual_entities == expected_entities


def test_nesteddirs(tmp_path: Path) -> None:
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

    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    expected_entities = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "datePublished": "2026-01-18T12:00:10+00:00",
                "hasPart": [{"@id": "input/nested/"}, {"@id": "output/processed/"}],
                "license": "CC-BY-4.0",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
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
    }
    assert actual_entities == expected_entities


def test_aargparse_value2path_stdin_handling():
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", type=argparse.FileType("r"))
    args = parser.parse_args(["-"])

    result = argparse_value2path(args.infile)

    assert result is None, "Expected None for stdin file argument"
    # Unable to test FileType('w') for stdout due to reading .name
    # causes `alueError: I/O operation on closed file.` while in pytest


# TODO add test that checks sub commands in argparse (e.g. git commit)
