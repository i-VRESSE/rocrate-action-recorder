import argparse
from datetime import datetime
import json
from pathlib import Path

import pytest
from rocrate_validator import services, models
from rocrate_validator.utils.uri import URI

import rocrate_action_recorder
from rocrate_action_recorder.parser import ArgparseRecorder, ArgparseArguments


def assert_crate_shape(crate_dir: Path) -> None:
    settings = models.ValidationSettings(
        rocrate_uri=URI(crate_dir),
        profile_identifier="process-run-crate",  # TODO use provenance-run-crate
        requirement_severity=models.Severity.RECOMMENDED,
    )
    result = services.validate(settings)
    assert result.passed()


@pytest.fixture
def parser():
    p = argparse.ArgumentParser(prog="myscript", description="Example CLI")
    p.add_argument("--input", type=Path, help="Input file")
    p.add_argument("--output", type=Path, help="Output file")
    return p


def test_record_happy_path_valid_crate(tmp_path, parser):
    crate_dir = tmp_path
    data_dir = crate_dir / "data"
    results_dir = crate_dir / "results"
    data_dir.mkdir()
    results_dir.mkdir()
    input_path = data_dir / "input.txt"
    output_path = results_dir / "output.txt"
    input_path.write_text("Hello World\n")
    # Build real argparse Namespace as in example/myscript.py
    args = parser.parse_args(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )
    # Use a fixed start_time and end_time for test reproducibility
    start_time = datetime(2026, 1, 16, 12, 0, 0)
    end_time = datetime(2026, 1, 16, 12, 0, 5)
    # Simulate the script's main operation
    output_path.write_text(input_path.read_text().upper())

    crate_meta = rocrate_action_recorder.record(
        args=ArgparseArguments(args),
        inputs=["input"],
        outputs=["output"],
        parser=ArgparseRecorder(parser),
        start_time=start_time,
        crate_dir=crate_dir,
        # Simulate calling from CLI
        argv=["myscript", "--input", str(input_path), "--output", str(output_path)],
        end_time=end_time,
        current_user="test_user",
        software_version="1.0.0",
        dataset_license="CC-BY-4.0",
    )

    assert crate_meta.exists(), (
        "record() did not produce ro-crate-metadata.json in crate_dir"
    )

    assert_crate_shape(crate_dir)

    expected_entities = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": "myscript actions",
            "description": "Example CLI",
            "hasPart": [{"@id": "data/input.txt"}, {"@id": "results/output.txt"}],
            "datePublished": "2026-01-16",
            "license": "CC-BY-4.0",
        },
        {"@id": "test_user", "@type": "Person", "name": "test_user"},
        {
            "@id": "myscript",
            "@type": "SoftwareApplication",
            "name": "myscript",
            "description": "Example CLI",
            "version": "1.0.0",
        },
        {
            "@id": f"myscript --input {input_path} --output {output_path}",
            "@type": "CreateAction",
            "name": "Example CLI",
            "startTime": "2026-01-16T12:00:00",
            "object": [{"@id": "data/input.txt"}],
            "instrument": {"@id": "myscript"},
            "endTime": "2026-01-16T12:00:05",
            "result": [{"@id": "results/output.txt"}],
            "agent": {"@id": "test_user"},
        },
        {
            "@id": "data/input.txt",
            "@type": "File",
            "name": "Input file",
            "encodingFormat": "text/plain",
            "contentSize": "12",
        },
        {
            "@id": "results/output.txt",
            "@type": "File",
            "name": "Output file",
            "encodingFormat": "text/plain",
            "contentSize": "12",
        },
    ]
    actual = json.loads(crate_meta.read_text(encoding="utf-8"))

    # Check context
    assert actual["@context"] == "https://w3id.org/ro/crate/1.1/context"

    # Check graph entities (order-independent comparison since RO-Crate is JSON-LD)
    actual_entities = {entity["@id"]: entity for entity in actual["@graph"]}
    expected_entities_dict = {entity["@id"]: entity for entity in expected_entities}

    assert set(actual_entities.keys()) == set(expected_entities_dict.keys()), (
        f"Entity IDs mismatch.\nActual: {set(actual_entities.keys())}\n"
        f"Expected: {set(expected_entities_dict.keys())}"
    )

    for entity_id, expected_entity in expected_entities_dict.items():
        actual_entity = actual_entities[entity_id]
        assert actual_entity == expected_entity, (
            f"Entity {entity_id} mismatch.\n"
            f"Expected: {expected_entity}\n"
            f"Actual: {actual_entity}"
        )


def test_record_updates_existing_action_and_files_on_repeat_command(tmp_path, parser):
    crate_dir = tmp_path
    data_dir = crate_dir / "data"
    results_dir = crate_dir / "results"
    data_dir.mkdir()
    results_dir.mkdir()

    input_path = data_dir / "input.txt"
    output_path = results_dir / "output.txt"

    # First run content
    input_path.write_text("Hello World\n", encoding="utf-8")

    args = parser.parse_args(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    start_time_1 = datetime(2026, 1, 16, 12, 0, 0)
    end_time_1 = datetime(2026, 1, 16, 12, 0, 5)

    # Simulate run work
    output_path.write_text(
        input_path.read_text(encoding="utf-8").upper(), encoding="utf-8"
    )

    argv = [
        "myscript",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]

    crate_meta_1 = rocrate_action_recorder.record(
        args=ArgparseArguments(args),
        inputs=["input"],
        outputs=["output"],
        parser=ArgparseRecorder(parser),
        start_time=start_time_1,
        crate_dir=crate_dir,
        argv=argv,
        end_time=end_time_1,
        current_user="test_user",
        software_version="1.0.0",
        dataset_license="CC-BY-4.0",
    )

    assert crate_meta_1.exists()

    # Second run with changed sizes and times
    input_path.write_text("Hello World!!!\n", encoding="utf-8")
    output_path.write_text(
        input_path.read_text(encoding="utf-8").upper(), encoding="utf-8"
    )

    start_time_2 = datetime(2026, 1, 16, 13, 0, 0)
    end_time_2 = datetime(2026, 1, 16, 13, 0, 7)

    crate_meta_2 = rocrate_action_recorder.record(
        args=ArgparseArguments(args),
        inputs=["input"],
        outputs=["output"],
        parser=ArgparseRecorder(parser),
        start_time=start_time_2,
        crate_dir=crate_dir,
        argv=argv,
        end_time=end_time_2,
        current_user="test_user",
        software_version="1.0.0",
        dataset_license="CC-BY-4.0",
    )

    assert crate_meta_2.exists()
    assert_crate_shape(crate_dir)

    data = json.loads(crate_meta_2.read_text(encoding="utf-8"))
    entities = {e["@id"]: e for e in data["@graph"]}

    action_id = f"myscript --input {input_path} --output {output_path}"
    assert action_id in entities

    # Ensure there is exactly one action with that id and it has updated times
    action_entity = entities[action_id]
    assert action_entity["startTime"] == "2026-01-16T13:00:00"
    assert action_entity["endTime"] == "2026-01-16T13:00:07"

    # Files should be de-duplicated and have updated sizes
    assert entities["data/input.txt"]["contentSize"] == str(
        (data_dir / "input.txt").stat().st_size
    )
    assert entities["results/output.txt"]["contentSize"] == str(
        (results_dir / "output.txt").stat().st_size
    )

    # Person and SoftwareApplication should be unique
    persons = [e for e in data["@graph"] if e.get("@type") == "Person"]
    softwares = [e for e in data["@graph"] if e.get("@type") == "SoftwareApplication"]
    assert len(persons) == 1
    assert len(softwares) == 1

    # Root dataset hasPart should list each file once
    dataset = entities["./"]
    has_part_ids = {p["@id"] for p in dataset.get("hasPart", [])}
    assert has_part_ids == {"data/input.txt", "results/output.txt"}


def test_record_rejects_paths_outside_crate_root(tmp_path, parser):
    crate_dir = tmp_path
    # make inside results dir but outside data file
    (crate_dir / "results").mkdir()
    outside = crate_dir.parent / "outside.txt"
    outside.write_text("data", encoding="utf-8")
    inside_output = crate_dir / "results" / "output.txt"

    args = parser.parse_args(
        [
            "--input",
            str(outside),
            "--output",
            str(inside_output),
        ]
    )

    with pytest.raises(ValueError):
        rocrate_action_recorder.record(
            args=ArgparseArguments(args),
            inputs=["input"],
            outputs=["output"],
            parser=ArgparseRecorder(parser),
            start_time=datetime(2026, 1, 16, 12, 0, 0),
            crate_dir=crate_dir,
            argv=["myscript", "--input", str(outside), "--output", str(inside_output)],
            end_time=datetime(2026, 1, 16, 12, 0, 5),
            current_user="test_user",
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

    assert not (crate_dir / "ro-crate-metadata.json").exists()


def test_record_dedup_person_and_softwareapplication(tmp_path, parser):
    crate_dir = tmp_path
    data_dir = crate_dir / "data"
    results_dir = crate_dir / "results"
    data_dir.mkdir()
    results_dir.mkdir()
    input_path = data_dir / "input.txt"
    output_path = results_dir / "output.txt"
    input_path.write_text("Hello\n", encoding="utf-8")

    args = parser.parse_args(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    argv = ["myscript", "--input", str(input_path), "--output", str(output_path)]

    # Run twice
    for i in range(2):
        output_path.write_text(
            input_path.read_text(encoding="utf-8").upper(), encoding="utf-8"
        )
        rocrate_action_recorder.record(
            args=ArgparseArguments(args),
            inputs=["input"],
            outputs=["output"],
            parser=ArgparseRecorder(parser),
            start_time=datetime(2026, 1, 16, 12, 0, 0),
            crate_dir=crate_dir,
            argv=argv,
            end_time=datetime(2026, 1, 16, 12, 0, 5),
            current_user="test_user",
            software_version="1.0.0",
            dataset_license="CC-BY-4.0",
        )

    crate_meta = crate_dir / "ro-crate-metadata.json"
    assert crate_meta.exists()
    data = json.loads(crate_meta.read_text(encoding="utf-8"))
    persons = [e for e in data["@graph"] if e.get("@type") == "Person"]
    softwares = [e for e in data["@graph"] if e.get("@type") == "SoftwareApplication"]
    assert len(persons) == 1
    assert len(softwares) == 1
