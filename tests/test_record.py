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
        input_files=["input"],
        output_files=["output"],
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
            "@id": "myscript@1.0.0",
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
            "instrument": {"@id": "myscript@1.0.0"},
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
        input_files=["input"],
        output_files=["output"],
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
        input_files=["input"],
        output_files=["output"],
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
            input_files=["input"],
            output_files=["output"],
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
            input_files=["input"],
            output_files=["output"],
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


def test_file_reuse_in_chain(tmp_path, parser):
    """Test that a file reused across multiple commands appears once in RO-Crate.

    Simulates a chain of commands where the output of the first command becomes
    the input to the second command. Verifies that the reused file is not
    duplicated and that both CreateActions correctly reference it.
    """
    crate_dir = tmp_path
    data_dir = crate_dir / "data"
    results_dir = crate_dir / "results"
    data_dir.mkdir()
    results_dir.mkdir()

    # Create input file for first command
    input_path = data_dir / "input.txt"
    input_path.write_text("Hello World\n", encoding="utf-8")

    # Intermediate file (output of first command, input to second)
    intermediate_path = results_dir / "output.txt"
    # Final output of second command
    final_output_path = results_dir / "output2.txt"

    # === FIRST COMMAND: input.txt → output.txt ===
    args1 = parser.parse_args(
        [
            "--input",
            str(input_path),
            "--output",
            str(intermediate_path),
        ]
    )

    start_time_1 = datetime(2026, 1, 16, 12, 0, 0)
    end_time_1 = datetime(2026, 1, 16, 12, 0, 5)
    argv1 = ["myscript", "--input", str(input_path), "--output", str(intermediate_path)]

    # Simulate first command execution
    intermediate_path.write_text(
        input_path.read_text(encoding="utf-8").upper(), encoding="utf-8"
    )

    rocrate_action_recorder.record(
        args=ArgparseArguments(args1),
        input_files=["input"],
        output_files=["output"],
        parser=ArgparseRecorder(parser),
        start_time=start_time_1,
        crate_dir=crate_dir,
        argv=argv1,
        end_time=end_time_1,
        current_user="test_user",
        software_version="1.0.0",
        dataset_license="CC-BY-4.0",
    )

    # === SECOND COMMAND: output.txt → output2.txt ===
    # Note: second command only READS output.txt (doesn't modify it)
    args2 = parser.parse_args(
        [
            "--input",
            str(intermediate_path),
            "--output",
            str(final_output_path),
        ]
    )

    start_time_2 = datetime(2026, 1, 16, 12, 1, 0)
    end_time_2 = datetime(2026, 1, 16, 12, 1, 3)
    argv2 = [
        "myscript",
        "--input",
        str(intermediate_path),
        "--output",
        str(final_output_path),
    ]

    # Simulate second command execution (just reverses the intermediate file)
    final_output_path.write_text(
        intermediate_path.read_text(encoding="utf-8")[::-1], encoding="utf-8"
    )

    rocrate_action_recorder.record(
        args=ArgparseArguments(args2),
        input_files=["input"],
        output_files=["output"],
        parser=ArgparseRecorder(parser),
        start_time=start_time_2,
        crate_dir=crate_dir,
        argv=argv2,
        end_time=end_time_2,
        current_user="test_user",
        software_version="1.0.0",
        dataset_license="CC-BY-4.0",
    )

    # === VERIFY RO-CRATE ===
    crate_meta = crate_dir / "ro-crate-metadata.json"
    assert crate_meta.exists()

    assert_crate_shape(crate_dir)

    data = json.loads(crate_meta.read_text(encoding="utf-8"))
    entities = {e["@id"]: e for e in data["@graph"]}

    # 1. Verify output.txt appears exactly once
    file_entities = [e for e in data["@graph"] if e.get("@type") == "File"]
    output_txt_entities = [e for e in file_entities if e["@id"] == "results/output.txt"]
    assert len(output_txt_entities) == 1, (
        f"output.txt should appear exactly once, found {len(output_txt_entities)}"
    )

    # 2. Verify output.txt metadata
    output_txt_entity = output_txt_entities[0]
    expected_size = str(intermediate_path.stat().st_size)
    assert output_txt_entity["contentSize"] == expected_size
    # Note: file name reflects its last role (input to second command)
    assert output_txt_entity["name"] == "Input file"
    assert output_txt_entity["encodingFormat"] == "text/plain"

    # 3. Verify first CreateAction
    action1_id = f"myscript --input {input_path} --output {intermediate_path}"
    action1 = entities[action1_id]
    assert action1["@type"] == "CreateAction"
    assert action1["startTime"] == "2026-01-16T12:00:00"
    assert action1["endTime"] == "2026-01-16T12:00:05"
    assert action1["agent"]["@id"] == "test_user"
    assert action1["instrument"]["@id"] == "myscript@1.0.0"

    # Check inputs and outputs reference correct files
    action1_object_ids = [obj["@id"] for obj in action1["object"]]
    action1_result_ids = [res["@id"] for res in action1["result"]]
    assert action1_object_ids == ["data/input.txt"]
    assert action1_result_ids == ["results/output.txt"]

    # 4. Verify second CreateAction
    action2_id = f"myscript --input {intermediate_path} --output {final_output_path}"
    action2 = entities[action2_id]
    assert action2["@type"] == "CreateAction"
    assert action2["startTime"] == "2026-01-16T12:01:00"
    assert action2["endTime"] == "2026-01-16T12:01:03"
    assert action2["agent"]["@id"] == "test_user"
    assert action2["instrument"]["@id"] == "myscript@1.0.0"

    # Check inputs and outputs reference correct files
    action2_object_ids = [obj["@id"] for obj in action2["object"]]
    action2_result_ids = [res["@id"] for res in action2["result"]]
    assert action2_object_ids == ["results/output.txt"], (
        f"Second action should reference results/output.txt as input, got {action2_object_ids}"
    )
    assert action2_result_ids == ["results/output2.txt"]

    # 5. Verify Person and SoftwareApplication are de-duplicated
    persons = [e for e in data["@graph"] if e.get("@type") == "Person"]
    softwares = [e for e in data["@graph"] if e.get("@type") == "SoftwareApplication"]
    assert len(persons) == 1
    assert len(softwares) == 1

    # 6. Verify Dataset has all three files in hasPart
    dataset = entities["./"]
    has_part_ids = {p["@id"] for p in dataset.get("hasPart", [])}
    assert has_part_ids == {
        "data/input.txt",
        "results/output.txt",
        "results/output2.txt",
    }


def test_record_adds_new_software_on_version_change(tmp_path, parser):
    """Test that different software versions are recorded as separate SoftwareApplication entities.

    Simulates two runs with the same script but different versions.
    Verifies that:
    - Two SoftwareApplication entities are created with versioned identifiers (name@version)
    - Each CreateAction references the correct SoftwareApplication version
    - Files and Person are still deduplicated appropriately
    """
    crate_dir = tmp_path
    data_dir = crate_dir / "data"
    results_dir = crate_dir / "results"
    data_dir.mkdir()
    results_dir.mkdir()

    input_path_1 = data_dir / "input.txt"
    output_path_1 = results_dir / "output.txt"
    input_path_1.write_text("Hello World\n", encoding="utf-8")

    # === FIRST RUN: version 1.0.0 ===
    args_1 = parser.parse_args(
        [
            "--input",
            str(input_path_1),
            "--output",
            str(output_path_1),
        ]
    )

    start_time_1 = datetime(2026, 1, 16, 12, 0, 0)
    end_time_1 = datetime(2026, 1, 16, 12, 0, 5)
    argv_1 = ["myscript", "--input", str(input_path_1), "--output", str(output_path_1)]

    output_path_1.write_text(
        input_path_1.read_text(encoding="utf-8").upper(), encoding="utf-8"
    )

    rocrate_action_recorder.record(
        args=ArgparseArguments(args_1),
        input_files=["input"],
        output_files=["output"],
        parser=ArgparseRecorder(parser),
        start_time=start_time_1,
        crate_dir=crate_dir,
        argv=argv_1,
        end_time=end_time_1,
        current_user="test_user",
        software_version="1.0.0",
        dataset_license="CC-BY-4.0",
    )

    # === SECOND RUN: version 2.0.0, different input/output ===
    input_path_2 = data_dir / "input2.txt"
    output_path_2 = results_dir / "output2.txt"
    input_path_2.write_text("Hello Again\n", encoding="utf-8")

    args_2 = parser.parse_args(
        [
            "--input",
            str(input_path_2),
            "--output",
            str(output_path_2),
        ]
    )

    start_time_2 = datetime(2026, 1, 16, 13, 0, 0)
    end_time_2 = datetime(2026, 1, 16, 13, 0, 5)
    argv_2 = ["myscript", "--input", str(input_path_2), "--output", str(output_path_2)]

    output_path_2.write_text(
        input_path_2.read_text(encoding="utf-8").upper(), encoding="utf-8"
    )

    rocrate_action_recorder.record(
        args=ArgparseArguments(args_2),
        input_files=["input"],
        output_files=["output"],
        parser=ArgparseRecorder(parser),
        start_time=start_time_2,
        crate_dir=crate_dir,
        argv=argv_2,
        end_time=end_time_2,
        current_user="test_user",
        software_version="2.0.0",
        dataset_license="CC-BY-4.0",
    )

    # === VERIFY RO-CRATE ===
    crate_meta = crate_dir / "ro-crate-metadata.json"
    assert crate_meta.exists()

    assert_crate_shape(crate_dir)

    data = json.loads(crate_meta.read_text(encoding="utf-8"))
    entities = {e["@id"]: e for e in data["@graph"]}

    # Verify both software versions exist with versioned identifiers
    softwares = [e for e in data["@graph"] if e.get("@type") == "SoftwareApplication"]
    assert len(softwares) == 2, (
        f"Expected 2 SoftwareApplication entities, found {len(softwares)}"
    )

    software_ids = {s["@id"] for s in softwares}
    assert software_ids == {"myscript@1.0.0", "myscript@2.0.0"}, (
        f"Expected versioned identifiers myscript@1.0.0 and myscript@2.0.0, got {software_ids}"
    )

    # Verify each SoftwareApplication has correct version property
    software_1_0 = entities["myscript@1.0.0"]
    assert software_1_0["version"] == "1.0.0"
    assert software_1_0["name"] == "myscript"
    assert software_1_0["description"] == "Example CLI"

    software_2_0 = entities["myscript@2.0.0"]
    assert software_2_0["version"] == "2.0.0"
    assert software_2_0["name"] == "myscript"
    assert software_2_0["description"] == "Example CLI"

    # Verify first CreateAction references version 1.0.0
    action_1_id = f"myscript --input {input_path_1} --output {output_path_1}"
    action_1 = entities[action_1_id]
    assert action_1["instrument"]["@id"] == "myscript@1.0.0"
    assert action_1["startTime"] == "2026-01-16T12:00:00"

    # Verify second CreateAction references version 2.0.0
    action_2_id = f"myscript --input {input_path_2} --output {output_path_2}"
    action_2 = entities[action_2_id]
    assert action_2["instrument"]["@id"] == "myscript@2.0.0"
    assert action_2["startTime"] == "2026-01-16T13:00:00"

    # Verify Person is still deduplicated
    persons = [e for e in data["@graph"] if e.get("@type") == "Person"]
    assert len(persons) == 1
    assert persons[0]["@id"] == "test_user"
