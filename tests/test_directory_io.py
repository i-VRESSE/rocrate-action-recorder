import argparse
from datetime import datetime
import json
from pathlib import Path

import pytest

import rocrate_action_recorder
from rocrate_action_recorder.parser import ArgparseRecorder, ArgparseArguments


@pytest.fixture
def dir_parser():
    """Parser with directory arguments."""
    p = argparse.ArgumentParser(prog="dirscript", description="Directory processor")
    p.add_argument("input_dir", type=Path, help="Input directory")
    p.add_argument("output_dir", type=Path, help="Output directory")
    return p


def test_record_directory_with_files_inside(tmp_path, dir_parser):
    """Test recording directories as inputs/outputs with files inside them."""
    crate_dir = tmp_path
    input_dir = crate_dir / "input_data"
    output_dir = crate_dir / "output_data"

    # Create directories
    input_dir.mkdir()
    output_dir.mkdir()

    # Create files inside input directory
    (input_dir / "file1.txt").write_text("content 1\n", encoding="utf-8")
    (input_dir / "file2.txt").write_text("content 2\n", encoding="utf-8")

    # Create files inside output directory
    (output_dir / "result1.txt").write_text("CONTENT 1\n", encoding="utf-8")
    (output_dir / "result2.txt").write_text("CONTENT 2\n", encoding="utf-8")

    args = dir_parser.parse_args([str(input_dir), str(output_dir)])

    start_time = datetime(2026, 1, 16, 12, 0, 0)
    end_time = datetime(2026, 1, 16, 12, 0, 5)

    crate_meta = rocrate_action_recorder.record(
        args=ArgparseArguments(args),
        input_dirs=["input_dir"],
        output_dirs=["output_dir"],
        parser=ArgparseRecorder(dir_parser),
        start_time=start_time,
        crate_dir=crate_dir,
        argv=["dirscript", str(input_dir), str(output_dir)],
        end_time=end_time,
        current_user="test_user",
        software_version="1.0.0",
        dataset_license="CC-BY-4.0",
    )

    assert crate_meta.exists()

    data = json.loads(crate_meta.read_text(encoding="utf-8"))
    entities = {e["@id"]: e for e in data["@graph"]}

    # Verify directories are in the crate (with trailing slash)
    assert "input_data/" in entities
    assert "output_data/" in entities

    # Verify directory entities have correct type
    assert entities["input_data/"]["@type"] == "Dataset"
    assert entities["output_data/"]["@type"] == "Dataset"

    # Verify directory entities have names
    assert entities["input_data/"]["name"] == "Input directory"
    assert entities["output_data/"]["name"] == "Output directory"

    # Verify directories do not have contentSize or encodingFormat
    assert "contentSize" not in entities["input_data/"]
    assert "encodingFormat" not in entities["input_data/"]
    assert "contentSize" not in entities["output_data/"]
    assert "encodingFormat" not in entities["output_data/"]

    # Verify CreateAction references directories
    action_id = f"dirscript {input_dir} {output_dir}"
    action = entities[action_id]
    assert action["@type"] == "CreateAction"

    action_object_ids = [obj["@id"] for obj in action["object"]]
    action_result_ids = [res["@id"] for res in action["result"]]

    assert action_object_ids == ["input_data/"]
    assert action_result_ids == ["output_data/"]


def test_record_mixed_files_and_directories(tmp_path):
    """Test recording both files and directories as inputs/outputs."""
    crate_dir = tmp_path

    # Create file arguments
    input_file = crate_dir / "config.txt"
    output_file = crate_dir / "report.txt"
    input_file.write_text("config data\n", encoding="utf-8")
    output_file.write_text("report data\n", encoding="utf-8")

    # Create directory arguments
    input_dir = crate_dir / "data"
    output_dir = crate_dir / "results"
    input_dir.mkdir()
    output_dir.mkdir()

    # Add files to directories
    (input_dir / "sample1.txt").write_text("sample 1\n", encoding="utf-8")
    (input_dir / "sample2.txt").write_text("sample 2\n", encoding="utf-8")
    (output_dir / "output1.txt").write_text("OUTPUT 1\n", encoding="utf-8")
    (output_dir / "output2.txt").write_text("OUTPUT 2\n", encoding="utf-8")

    # Parser with mixed arguments
    parser = argparse.ArgumentParser(
        prog="mixedscript", description="Mixed file and directory processor"
    )
    parser.add_argument("--config", type=Path, help="Config file")
    parser.add_argument("--data-dir", type=Path, help="Data directory")
    parser.add_argument("--output-dir", type=Path, help="Output directory")
    parser.add_argument("--report", type=Path, help="Report file")

    args = parser.parse_args(
        [
            "--config",
            str(input_file),
            "--data-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--report",
            str(output_file),
        ]
    )

    start_time = datetime(2026, 1, 16, 12, 0, 0)
    end_time = datetime(2026, 1, 16, 12, 0, 10)

    crate_meta = rocrate_action_recorder.record(
        args=ArgparseArguments(args),
        input_files=["config"],
        input_dirs=["data_dir"],
        output_dirs=["output_dir"],
        output_files=["report"],
        parser=ArgparseRecorder(parser),
        start_time=start_time,
        crate_dir=crate_dir,
        argv=[
            "mixedscript",
            "--config",
            str(input_file),
            "--data-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--report",
            str(output_file),
        ],
        end_time=end_time,
        current_user="test_user",
        software_version="1.0.0",
    )

    assert crate_meta.exists()

    data = json.loads(crate_meta.read_text(encoding="utf-8"))
    entities = {e["@id"]: e for e in data["@graph"]}

    # Verify all entities exist (directories have trailing slash)
    assert "config.txt" in entities
    assert "data/" in entities
    assert "results/" in entities
    assert "report.txt" in entities

    # Verify types
    assert entities["config.txt"]["@type"] == "File"
    assert entities["data/"]["@type"] == "Dataset"
    assert entities["results/"]["@type"] == "Dataset"
    assert entities["report.txt"]["@type"] == "File"

    # Verify CreateAction references both files and directories
    action_id = (
        f"mixedscript --config {input_file} --data-dir {input_dir} "
        f"--output-dir {output_dir} --report {output_file}"
    )
    action = entities[action_id]

    action_object_ids = [obj["@id"] for obj in action["object"]]
    action_result_ids = [res["@id"] for res in action["result"]]

    # Order: files first, then directories
    assert set(action_object_ids) == {"config.txt", "data/"}
    assert set(action_result_ids) == {"results/", "report.txt"}


def test_record_directory_deduplication(tmp_path):
    """Test that directories are deduplicated across multiple record calls."""
    crate_dir = tmp_path
    input_dir = crate_dir / "shared_data"
    output_dir = crate_dir / "results"

    input_dir.mkdir()
    output_dir.mkdir()

    # Add files
    (input_dir / "data.txt").write_text("data\n", encoding="utf-8")
    (output_dir / "output1.txt").write_text("output 1\n", encoding="utf-8")

    parser = argparse.ArgumentParser(prog="dedupscript", description="Dedup test")
    parser.add_argument("input_dir", type=Path, help="Input directory")
    parser.add_argument("output_dir", type=Path, help="Output directory")

    args = parser.parse_args([str(input_dir), str(output_dir)])

    # First run
    rocrate_action_recorder.record(
        args=ArgparseArguments(args),
        input_dirs=["input_dir"],
        output_dirs=["output_dir"],
        parser=ArgparseRecorder(parser),
        start_time=datetime(2026, 1, 16, 12, 0, 0),
        crate_dir=crate_dir,
        argv=["dedupscript", str(input_dir), str(output_dir)],
        end_time=datetime(2026, 1, 16, 12, 0, 5),
        current_user="test_user",
        software_version="1.0.0",
    )

    # Second run (same directories)
    (output_dir / "output2.txt").write_text("output 2\n", encoding="utf-8")

    rocrate_action_recorder.record(
        args=ArgparseArguments(args),
        input_dirs=["input_dir"],
        output_dirs=["output_dir"],
        parser=ArgparseRecorder(parser),
        start_time=datetime(2026, 1, 16, 13, 0, 0),
        crate_dir=crate_dir,
        argv=["dedupscript", str(input_dir), str(output_dir)],
        end_time=datetime(2026, 1, 16, 13, 0, 5),
        current_user="test_user",
        software_version="1.0.0",
    )

    crate_meta = crate_dir / "ro-crate-metadata.json"
    data = json.loads(crate_meta.read_text(encoding="utf-8"))

    # Count directory entities (directories have trailing slash)
    dir_entities = [
        e
        for e in data["@graph"]
        if e.get("@type") == "Dataset" and e.get("@id") in ["shared_data/", "results/"]
    ]

    # Each directory should appear exactly once
    dir_ids = [e["@id"] for e in dir_entities]
    assert dir_ids.count("shared_data/") == 1
    assert dir_ids.count("results/") == 1


def test_record_rejects_directory_paths_outside_crate_root(tmp_path):
    """Test that directories outside crate root are rejected."""
    crate_dir = tmp_path
    output_dir = crate_dir / "results"
    output_dir.mkdir()

    # Create directory outside crate root
    outside_dir = crate_dir.parent / "outside_data"
    outside_dir.mkdir()
    (outside_dir / "data.txt").write_text("data\n", encoding="utf-8")

    parser = argparse.ArgumentParser(prog="pathscript", description="Path validation")
    parser.add_argument("input_dir", type=Path, help="Input directory")
    parser.add_argument("output_dir", type=Path, help="Output directory")

    args = parser.parse_args([str(outside_dir), str(output_dir)])

    with pytest.raises(ValueError, match="outside the crate root"):
        rocrate_action_recorder.record(
            args=ArgparseArguments(args),
            input_dirs=["input_dir"],
            output_dirs=["output_dir"],
            parser=ArgparseRecorder(parser),
            start_time=datetime(2026, 1, 16, 12, 0, 0),
            crate_dir=crate_dir,
            argv=["pathscript", str(outside_dir), str(output_dir)],
            end_time=datetime(2026, 1, 16, 12, 0, 5),
            current_user="test_user",
            software_version="1.0.0",
        )

    assert not (crate_dir / "ro-crate-metadata.json").exists()
