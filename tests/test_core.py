import importlib.metadata
import json
from pathlib import Path

from rocrate_validator import services, models
from rocrate_validator.utils.uri import URI

from rocrate_action_recorder.core import detect_software_version, playback


def assert_crate_shape(crate_dir: Path) -> None:
    settings = models.ValidationSettings(
        rocrate_uri=URI(crate_dir),
        profile_identifier="process-run-crate",
        requirement_severity=models.Severity.RECOMMENDED,
    )
    result = services.validate(settings)
    assert result.passed()


def test_detect_software_version_unknown():
    result = detect_software_version("non_existent_script_12345")
    assert result == ""


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
