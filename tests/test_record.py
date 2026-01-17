from argparse import ArgumentParser
import json
from pathlib import Path
from datetime import UTC, datetime

from rocrate_validator import services, models
from rocrate_validator.utils.uri import URI

from rocrate_action_recorder import record_with_argparse, IOs


def assert_crate_shape(crate_dir: Path) -> None:
    settings = models.ValidationSettings(
        rocrate_uri=URI(crate_dir),
        # TODO use more comprehensive provenance-run-crate profile
        profile_identifier="process-run-crate",
        requirement_severity=models.Severity.RECOMMENDED,
    )
    result = services.validate(settings)
    assert result.passed()


def test_record_with_argparse_onein_oneout_abspaths(tmp_path: Path):
    parser = ArgumentParser(prog="myscript", description="Example CLI")
    parser.add_argument("--input", type=Path, help="Input file")
    parser.add_argument("--output", type=Path, help="Output file")
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
