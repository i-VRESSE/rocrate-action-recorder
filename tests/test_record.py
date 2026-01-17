from argparse import ArgumentParser
import json
from pathlib import Path
from datetime import UTC, datetime

import pytest
from rocrate_validator import services, models
from rocrate_validator.utils.uri import URI

from rocrate_action_recorder import record_with_argparse, IOs


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


def test_record_with_argparse_onein_oneout_abspaths(tmp_path: Path,sample_argument_parser: ArgumentParser):
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

    assert (
        crate_meta.exists()
    ), "record() did not produce ro-crate-metadata.json in crate_dir"
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

    assert crate_meta.exists()
    assert_crate_shape(crate_dir)
    
    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    graph = actual_entities["@graph"]
    
    # Verify two distinct CreateAction entities exist
    actions = [e for e in graph if e.get("@type") == "CreateAction"]
    assert len(actions) == 2, f"Expected 2 CreateAction entities, got {len(actions)}"
    
    # Verify actions have different command IDs
    action_ids = {a["@id"] for a in actions}
    assert len(action_ids) == 2, "Action IDs should be unique"
    
    # Verify all four files are included
    files = [e for e in graph if e.get("@type") == "File"]
    file_ids = {f["@id"] for f in files}
    assert file_ids == {"input.txt", "output.txt", "input2.txt", "output2.txt"}
    
    # Verify root dataset includes all files
    root = next(e for e in graph if e.get("@id") == "./")
    hasPart = {part["@id"] for part in root["hasPart"]}
    assert hasPart == {"input.txt", "output.txt", "input2.txt", "output2.txt"}


def test_record_same_input_different_output(tmp_path: Path, sample_argument_parser: ArgumentParser):
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

    assert crate_meta.exists()
    assert_crate_shape(crate_dir)
    
    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    graph = actual_entities["@graph"]
    
    # Verify two distinct CreateAction entities exist
    actions = [e for e in graph if e.get("@type") == "CreateAction"]
    assert len(actions) == 2, f"Expected 2 CreateAction entities, got {len(actions)}"
    
    # Verify input.txt is referenced by both actions
    input_refs = []
    for action in actions:
        input_objs = [obj["@id"] for obj in action.get("object", [])]
        input_refs.extend(input_objs)
    assert input_refs.count("data.txt") == 2, "Input file should be referenced by both actions"
    
    # Verify three files total: shared input + two outputs
    files = [e for e in graph if e.get("@type") == "File"]
    file_ids = {f["@id"] for f in files}
    assert file_ids == {"data.txt", "output1.txt", "output2.txt"}
    
    # Verify root dataset includes all files (no duplication)
    root = next(e for e in graph if e.get("@id") == "./")
    hasPart = {part["@id"] for part in root["hasPart"]}
    assert hasPart == {"data.txt", "output1.txt", "output2.txt"}


def test_record_same_command_twice(tmp_path: Path, sample_argument_parser: ArgumentParser):
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

    assert crate_meta.exists()
    assert_crate_shape(crate_dir)
    
    actual_entities = json.loads(crate_meta.read_text(encoding="utf-8"))
    graph = actual_entities["@graph"]
    
    # Verify only one CreateAction exists (second call is skipped)
    actions = [e for e in graph if e.get("@type") == "CreateAction"]
    assert len(actions) == 1, f"Expected 1 CreateAction (duplicate skipped), got {len(actions)}"
    
    # Verify the action references correct files
    action = actions[0]
    assert action["object"] == [{"@id": "input.txt"}]
    assert action["result"] == [{"@id": "output.txt"}]
