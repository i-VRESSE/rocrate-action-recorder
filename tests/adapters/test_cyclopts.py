import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, cast

import cyclopts
import pytest
from cyclopts import App, Parameter
from cyclopts.types import StdioPath, ExistingDirectory, NonExistentDirectory
from pydantic import BaseModel

from rocrate_action_recorder.adapters.cyclopts import (
    INPUT_DIR,
    INPUT_DIRS,
    INPUT_FILE,
    INPUT_FILES,
    OUTPUT_DIR,
    OUTPUT_DIRS,
    OUTPUT_FILE,
    OUTPUT_FILES,
    RECORD_TRIGGER,
    program_from_app,
    run_with_record,
)
from rocrate_action_recorder.adapters.shared import value2paths as cyclopts_value2paths
from rocrate_action_recorder.core import Program


def assert_crate(
    tmp_path: Path,
    *,
    expected_action_id: str | None = None,
    expected_input_ids: set[str] | None = None,
    expected_output_ids: set[str] | None = None,
    excluded_input_ids: set[str] | None = None,
    excluded_output_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    crate_path = tmp_path / "ro-crate-metadata.json"
    assert crate_path.exists()

    if (
        expected_action_id is None
        and expected_input_ids is None
        and expected_output_ids is None
        and excluded_input_ids is None
        and excluded_output_ids is None
    ):
        return {}

    graph = cast(
        dict[str, dict[str, Any]],
        {entry["@id"]: entry for entry in json.loads(crate_path.read_text())["@graph"]},
    )
    action = next(
        entry for entry in graph.values() if entry.get("@type") == "CreateAction"
    )

    if expected_action_id is not None:
        assert action["@id"] == expected_action_id
        assert action["name"] == expected_action_id

    input_ids = {
        entry["@id"] for entry in cast(list[dict[str, str]], action.get("object", []))
    }
    output_ids = {
        entry["@id"] for entry in cast(list[dict[str, str]], action.get("result", []))
    }

    if expected_input_ids is not None:
        assert expected_input_ids <= input_ids

    if expected_output_ids is not None:
        assert expected_output_ids <= output_ids

    if excluded_input_ids is not None:
        assert excluded_input_ids.isdisjoint(input_ids)

    if excluded_output_ids is not None:
        assert excluded_output_ids.isdisjoint(output_ids)

    return graph


@pytest.fixture
def working_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestRunWithRecord:
    class TestMarkers:
        def test_single_input_output_file(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            input_fn = input_file.name
            output_file = working_tmp_path / "output.txt"
            output_fn = output_file.name

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                return output.write_text(input.read_text().upper())

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[input_fn, output_fn],
            )

            assert result == 5
            assert output_file.read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_action_id=f"myfunc {input_fn} {output_fn}",
                expected_input_ids={input_fn},
                expected_output_ids={output_fn},
            )

        def test_multiple_input_files(self, working_tmp_path: Path):
            input_file_1 = working_tmp_path / "input1.txt"
            input_fn1 = input_file_1.name
            input_file_2 = working_tmp_path / "input2.txt"
            input_fn2 = input_file_2.name
            input_file_1.write_text("hello")
            input_file_2.write_text("world")
            output_file = working_tmp_path / "output.txt"
            output_fn = output_file.name

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                *,
                input_files: Annotated[list[Path], INPUT_FILES],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                combined = "\n".join(path.read_text().upper() for path in input_files)
                return output.write_text(combined)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[
                    "--input-files",
                    input_fn1,
                    "--input-files",
                    input_fn2,
                    "--output",
                    output_fn,
                ],
            )

            assert result == 11
            assert output_file.read_text() == "HELLO\nWORLD"
            assert_crate(
                working_tmp_path,
                expected_action_id=f"myfunc --input-files {input_fn1} --input-files {input_fn2} --output {output_fn}",
                expected_input_ids={"input1.txt", "input2.txt"},
            )

        def test_multiple_output_files(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_fn = input_file.name
            input_file.write_text("hello")
            output_file_1 = working_tmp_path / "output1.txt"
            output_fn1 = output_file_1.name
            output_file_2 = working_tmp_path / "output2.txt"
            output_fn2 = output_file_2.name

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                *,
                input: Annotated[Path, INPUT_FILE],
                output_files: Annotated[list[Path], OUTPUT_FILES],
            ):
                data = input.read_text().upper()
                return sum(output.write_text(data) for output in output_files)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[
                    "--input",
                    input_fn,
                    "--output-files",
                    output_fn1,
                    "--output-files",
                    output_fn2,
                ],
            )

            assert result == 10
            assert output_file_1.read_text() == "HELLO"
            assert output_file_2.read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_action_id=f"myfunc --input {input_fn} --output-files {output_fn1} --output-files {output_fn2}",
                expected_input_ids={input_fn},
                expected_output_ids={output_fn1, output_fn2},
            )

        def test_single_input_output_dir(self, working_tmp_path: Path):
            input_dir = working_tmp_path / "input"
            input_dir.mkdir()
            input_fn = input_dir.name
            (input_dir / "a.txt").write_text("hello")
            output_dir = working_tmp_path / "output"
            output_fn = output_dir.name

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input_dir_arg: Annotated[ExistingDirectory, INPUT_DIR],
                output_dir_arg: Annotated[NonExistentDirectory, OUTPUT_DIR],
            ):
                output_dir_arg.mkdir()
                content = (input_dir_arg / "a.txt").read_text().upper()
                return (output_dir_arg / "a.txt").write_text(content)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[input_fn, output_fn],
            )

            assert result == 5
            assert (output_dir / "a.txt").read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_action_id=f"myfunc {input_fn} {output_fn}",
                expected_input_ids={"input/"},
                expected_output_ids={"output/"},
            )

        def test_multiple_input_dirs(self, working_tmp_path: Path):
            input_dir_1 = working_tmp_path / "input1"
            input_dir_2 = working_tmp_path / "input2"
            input_dir_1.mkdir()
            input_dir_2.mkdir()
            (input_dir_1 / "a.txt").write_text("hello")
            (input_dir_2 / "b.txt").write_text("world")
            output_file = working_tmp_path / "output.txt"

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                *,
                input_dirs: Annotated[list[Path], INPUT_DIRS],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                combined = "\n".join(
                    sorted(
                        (path / next(path.iterdir()).name).read_text().upper()
                        for path in input_dirs
                    )
                )
                return output.write_text(combined)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[
                    "--input-dirs",
                    str(input_dir_1),
                    "--input-dirs",
                    str(input_dir_2),
                    "--output",
                    str(output_file),
                ],
            )

            assert result == 11
            assert output_file.read_text() == "HELLO\nWORLD"
            assert_crate(
                working_tmp_path,
                expected_input_ids={"input1/", "input2/"},
                expected_output_ids={"output.txt"},
            )

        def test_multiple_output_dirs(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_dir_1 = working_tmp_path / "output1"
            output_dir_2 = working_tmp_path / "output2"

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                *,
                input: Annotated[Path, INPUT_FILE],
                output_dirs: Annotated[list[Path], OUTPUT_DIRS],
            ):
                data = input.read_text().upper()
                total = 0
                for output_dir in output_dirs:
                    output_dir.mkdir()
                    total += (output_dir / "result.txt").write_text(data)
                return total

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[
                    "--input",
                    str(input_file),
                    "--output-dirs",
                    str(output_dir_1),
                    "--output-dirs",
                    str(output_dir_2),
                ],
            )

            assert result == 10
            assert (output_dir_1 / "result.txt").read_text() == "HELLO"
            assert (output_dir_2 / "result.txt").read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_output_ids={"output1/", "output2/"},
                expected_input_ids={"input.txt"},
            )

    class TestRecordTrigger:
        @pytest.fixture
        def app_with_record_trigger(self, working_tmp_path: Path):
            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                /,
                *,
                prov: Annotated[bool, RECORD_TRIGGER] = False,
            ):
                return output.write_text(input.read_text().upper())

            return app

        def test_record_trigger_default_off(
            self, working_tmp_path: Path, app_with_record_trigger: App
        ):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file = working_tmp_path / "output.txt"

            result = run_with_record(
                app_with_record_trigger,
                dataset_license="CC-BY-4.0",
                tokens=[str(input_file), str(output_file)],
            )

            assert result == 5
            assert output_file.read_text() == "HELLO"
            assert not (working_tmp_path / "ro-crate-metadata.json").exists()

        def test_record_trigger_on(
            self, working_tmp_path: Path, app_with_record_trigger: App
        ):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file = working_tmp_path / "output.txt"

            result = run_with_record(
                app_with_record_trigger,
                dataset_license="CC-BY-4.0",
                tokens=["--prov", str(input_file), str(output_file)],
            )

            assert result == 5
            assert output_file.read_text() == "HELLO"
            assert (working_tmp_path / "ro-crate-metadata.json").exists()

        def test_no_io_markers_raises_value_error(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file = working_tmp_path / "output.txt"

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input: Path,
                output: Path,
            ):
                return output.write_text(input.read_text().upper())

            with pytest.raises(ValueError, match="No arguments with INPUT_FILE"):
                run_with_record(
                    app,
                    dataset_license="CC-BY-4.0",
                    tokens=[str(input_file), str(output_file)],
                )

    class TestTypes:
        def test_stdiopath_dash_not_recorded(
            self,
            working_tmp_path: Path,
            caplog: pytest.LogCaptureFixture,
        ):
            output_file = working_tmp_path / "output.txt"

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input: Annotated[StdioPath, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                return output.write_text("from stdin")

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["-", str(output_file)],
            )

            assert result == 10
            assert output_file.read_text() == "from stdin"
            assert_crate(
                working_tmp_path,
                expected_output_ids={"output.txt"},
                excluded_input_ids={"-"},
            )
            assert (
                "Unable to convert stdin/stdout file-like object to Path, ignoring it"
                in caplog.text
            )
            assert "has no associated path-like argument value(s)." in caplog.text

        def test_nonexistent_output_path_in_admin_grouped_commands(
            self,
            working_tmp_path: Path,
            capsys: pytest.CaptureFixture[str],
        ):
            output_file = working_tmp_path / "downloaded.txt"
            url = "https://example.org/resource.txt"

            app = App(result_action="return_value", version="1.0.0")

            # Move built-in meta commands into the same command group as "info".
            app["--help"].group = "Admin"
            app["--version"].group = "Admin"

            @app.command(group="Admin")
            def info():
                """Print debugging system information."""
                print("Displaying system info.")

            @app.command
            def download(
                path: Annotated[cyclopts.types.NonExistentPath, OUTPUT_FILE],
                url: str,
            ):
                """Download a file."""
                path.write_text(f"fetched from {url}\n")
                print(f"Downloading {url} to {path}.")

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["download", str(output_file), url],
            )

            assert result is None
            assert f"Downloading {url} to {output_file}." in capsys.readouterr().out
            assert_crate(
                working_tmp_path,
                expected_output_ids={"downloaded.txt"},
            )

    class TestResultAction:
        def test_return_value(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file = working_tmp_path / "output.txt"

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                return output.write_text(input.read_text().upper())

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[str(input_file), str(output_file)],
            )

            assert result == 5
            assert output_file.read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )

        def test_print_non_int_return_int_as_exit_code(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file = working_tmp_path / "output.txt"

            app = App(
                result_action="print_non_int_return_int_as_exit_code", version="1.0.0"
            )

            @app.default
            def myfunc(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                output.write_text(input.read_text().upper())
                return 0

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[str(input_file), str(output_file)],
            )

            assert result == 0
            assert output_file.read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )

        def test_default_sys_exit(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file = working_tmp_path / "output.txt"

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                return output.write_text(input.read_text().upper())

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[str(input_file), str(output_file)],
            )

            assert result == 5
            assert output_file.read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )

        def test_print_non_int_sys_exit(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file = working_tmp_path / "output.txt"

            app = App(result_action="print_non_int_sys_exit", version="1.0.0")

            @app.default
            def myfunc(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                return output.write_text(input.read_text().upper())

            with pytest.raises(SystemExit) as exc_info:
                run_with_record(
                    app,
                    dataset_license="CC-BY-4.0",
                    tokens=[str(input_file), str(output_file)],
                )

            assert exc_info.value.code == 5
            assert output_file.read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )

    class TestSingleLevelSubcommand:
        def test_subcommand_single_level(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            app = App(name="myapp", result_action="return_value")

            @app.command
            def process(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                "Process files."
                output.write_text(input.read_text().upper())

            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", str(input_file), str(output_file)],
            )

            expected_action_id = f"myapp process {input_file} {output_file}"
            graph = assert_crate(
                working_tmp_path,
                expected_action_id=expected_action_id,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )
            assert not any("schema" in eid for eid in graph)

        def test_subcommand_with_trigger(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            app = App(name="myapp", result_action="return_value")

            @app.command
            def process(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                *,
                prov: Annotated[bool, RECORD_TRIGGER] = False,
            ):
                "Process files."
                output.write_text(input.read_text().upper())
                return output.stat().st_size

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", "--prov", str(input_file), str(output_file)],
            )

            assert result == 4
            assert output_file.read_text() == "DATA"
            expected_action_id = f"myapp process --prov {input_file} {output_file}"
            assert_crate(
                working_tmp_path,
                expected_action_id=expected_action_id,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )

        def test_subcommand_with_trigger_in_dataclass_on(
            self,
            working_tmp_path: Path,
        ):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            @Parameter(name="*")
            @dataclass
            class Common:
                prov: Annotated[bool, RECORD_TRIGGER] = False

            app = App(name="myapp", result_action="return_value")

            @app.command
            def process(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                *,
                common: Common | None = None,
            ):
                "Process files."
                output.write_text(input.read_text().upper())
                return output.stat().st_size

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", "--prov", str(input_file), str(output_file)],
            )

            assert result == 4
            crate_path = working_tmp_path / "ro-crate-metadata.json"
            assert crate_path.exists()
            # TODO use assert_crate

        def test_subcommand_with_trigger_in_dataclass_off(
            self,
            working_tmp_path: Path,
        ):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            @Parameter(name="*")
            @dataclass
            class Common:
                prov: Annotated[bool, RECORD_TRIGGER] = False

            app = App(name="myapp", result_action="return_value")

            @app.command
            def process(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                *,
                common: Common | None = None,
            ):
                "Process files."
                output.write_text(input.read_text().upper())
                return output.stat().st_size

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", str(input_file), str(output_file)],
            )

            assert result == 4
            crate_path = working_tmp_path / "ro-crate-metadata.json"
            assert not crate_path.exists()

    class TestTwoLevelSubcommand:
        def test_subcommand_two_levels(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            app = App(name="myapp", result_action="return_value")
            remote = App(name="remote")

            @remote.command
            def add(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
            ):
                "Add a remote."
                output.write_text(input.read_text().upper())

            app.command(remote)

            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", str(input_file), str(output_file)],
            )

            expected_action_id = f"myapp remote add {input_file} {output_file}"
            graph = assert_crate(
                working_tmp_path,
                expected_action_id=expected_action_id,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )
            assert not any("schema" in eid for eid in graph)

        def test_subcommand_two_levels_with_trigger(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            app = App(name="myapp", result_action="return_value")
            remote = App(name="remote")

            @remote.command
            def add(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                *,
                prov: Annotated[bool, RECORD_TRIGGER] = False,
            ):
                "Add a remote."
                output.write_text(input.read_text().upper())
                return output.stat().st_size

            app.command(remote)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", "--prov", str(input_file), str(output_file)],
            )

            assert result == 4
            assert output_file.read_text() == "DATA"
            expected_action_id = f"myapp remote add --prov {input_file} {output_file}"
            assert_crate(
                working_tmp_path,
                expected_action_id=expected_action_id,
                expected_input_ids={"input.txt"},
                expected_output_ids={"output.txt"},
            )

        def test_subcommand_two_levels_with_trigger_in_dataclass_on(
            self,
            working_tmp_path: Path,
        ):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            @Parameter(name="*")
            @dataclass
            class Common:
                prov: Annotated[bool, RECORD_TRIGGER] = False

            app = App(name="myapp", result_action="return_value")
            remote = App(name="remote")

            @remote.command
            def add(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                *,
                common: Common | None = None,
            ):
                "Add a remote."
                output.write_text(input.read_text().upper())
                return output.stat().st_size

            app.command(remote)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", "--prov", str(input_file), str(output_file)],
            )

            assert result == 4
            crate_path = working_tmp_path / "ro-crate-metadata.json"
            assert crate_path.exists()

        def test_subcommand_two_levels_with_trigger_in_dataclass_off(
            self,
            working_tmp_path: Path,
        ):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("data")
            output_file = working_tmp_path / "output.txt"

            @Parameter(name="*")
            @dataclass
            class Common:
                prov: Annotated[bool, RECORD_TRIGGER] = False

            app = App(name="myapp", result_action="return_value")
            remote = App(name="remote")

            @remote.command
            def add(
                input: Annotated[Path, INPUT_FILE],
                output: Annotated[Path, OUTPUT_FILE],
                *,
                common: Common | None = None,
            ):
                "Add a remote."
                output.write_text(input.read_text().upper())
                return output.stat().st_size

            app.command(remote)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", str(input_file), str(output_file)],
            )

            assert result == 4
            crate_path = working_tmp_path / "ro-crate-metadata.json"
            assert not crate_path.exists()


class TestPydanticNestedIO:
    def test_pydantic_nested_model(self, working_tmp_path: Path):
        """Test that nested Pydantic models with Path fields work."""
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        class IOConfig(BaseModel):
            input: Annotated[Path, INPUT_FILE]
            output: Annotated[Path, OUTPUT_FILE]

        class Config(BaseModel):
            io: IOConfig

        app = App(name="myapp", result_action="return_value")

        @app.default
        def main(config: Config):
            """Main command with nested Pydantic config."""
            config.io.output.write_text(config.io.input.read_text().upper())
            return 10

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[input_file.name, output_file.name],
        )

        assert result == 10
        assert output_file.read_text() == "DATA"
        assert_crate(
            working_tmp_path,
            expected_input_ids={"input.txt"},
            expected_output_ids={"output.txt"},
            # TODO fix action id
            # expected_action_id=f"myapp {input_file.name} {output_file.name}",
        )

    def test_pydantic_simple_model(self, working_tmp_path: Path):
        """Test that simple Pydantic models with Path fields work."""
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        class Config(BaseModel):
            input: Annotated[Path, INPUT_FILE]
            output: Annotated[Path, OUTPUT_FILE]

        app = App(name="myapp", result_action="return_value")

        @app.default
        def main(config: Config):
            """Main command with Pydantic config."""
            config.output.write_text(config.input.read_text().upper())
            return 4

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[str(input_file), str(output_file)],
        )

        assert result == 4
        assert output_file.read_text() == "DATA"
        assert_crate(
            working_tmp_path,
            expected_input_ids={"input.txt"},
            expected_output_ids={"output.txt"},
        )

    def test_pydantic_with_record_trigger(self, working_tmp_path: Path):
        """Test that Pydantic models with RECORD_TRIGGER work."""
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        class Config(BaseModel):
            input: Annotated[Path, INPUT_FILE]
            output: Annotated[Path, OUTPUT_FILE]
            prov: Annotated[bool, RECORD_TRIGGER] = False

        app = App(name="myapp", result_action="return_value")

        @app.default
        def main(config: Config):
            """Main command with Pydantic config and trigger."""
            config.output.write_text(config.input.read_text().upper())
            return 4

        # With trigger off
        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[str(input_file), str(output_file)],
        )
        assert result == 4
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()

        # With trigger on - nested Pydantic fields use dot notation
        run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["--config.prov", str(input_file), str(output_file)],
        )
        assert (working_tmp_path / "ro-crate-metadata.json").exists()


class TestProgramFromApp:
    def test_from_app_name(self):
        app = App(name="myapp", version="1.0.0", help="Help for myapp.")

        @app.default
        def process(input: Path, output: Path):
            """Process files."""
            pass

        result = program_from_app(app)

        expected = Program(
            name="myapp",
            version="1.0.0",
            description="Help for myapp.",
            subcommands={},
        )

        assert result == expected

    def test_from_default(self):
        app = App(version="1.0.0")

        @app.default
        def process(input: Path, output: Path):
            """Process files."""
            pass

        result = program_from_app(app)

        expected = Program(
            name="process",
            version="1.0.0",
            description="Process files.",
            subcommands={},
        )

        assert result == expected

    def test_single_level_subcommand(self):
        app = App(name="myapp", version="1.0.0")

        @app.command
        def process(input: Path, output: Path):
            """Process files."""
            pass

        program = program_from_app(app)

        # TODO asert against expected_program instead of individual fields
        assert program.name == "myapp"
        assert program.version == "1.0.0"
        assert "process" in program.subcommands
        assert program.subcommands["process"].name == "myapp process"
        # Subcommand inherits parent version when not specified
        assert program.subcommands["process"].version == "1.0.0"
        assert program.subcommands["process"].description == "Process files."

    def test_single_level_subcommand_no_version(self):
        app = App(name="myapp")

        @app.command
        def process(input: Path, output: Path):
            """Process files."""
            pass

        program = program_from_app(app)

        assert program.name == "myapp"
        assert program.version is None
        assert "process" in program.subcommands
        assert program.subcommands["process"].name == "myapp process"
        assert program.subcommands["process"].version is None
        assert program.subcommands["process"].description == "Process files."

    def test_two_level_nested_subcommand(self):
        app = App(name="myapp", version="1.0.0")
        remote = App(name="remote", version="2.0.0")

        @remote.command
        def add(input: Path, output: Path):
            """Add a remote."""
            pass

        app.command(remote)

        program = program_from_app(app)

        assert program.name == "myapp"
        assert "add" in program.subcommands
        assert program.subcommands["add"].name == "myapp remote add"
        assert program.subcommands["add"].version == "2.0.0"
        assert program.subcommands["add"].description == "Add a remote."

    def test_three_level_nested_subcommand(self):
        app = App(name="myapp", version="1.0.0")
        group = App(name="group", version="1.1.0")
        remote = App(name="remote", version="2.0.0")

        @remote.command
        def add(input: Path, output: Path):
            """Add a remote."""
            pass

        group.command(remote)
        app.command(group)

        program = program_from_app(app)

        assert program.name == "myapp"
        assert "add" in program.subcommands
        assert program.subcommands["add"].name == "myapp group remote add"
        assert program.subcommands["add"].version == "2.0.0"
        assert program.subcommands["add"].description == "Add a remote."

    def test_flattened_subcommand(self):
        app = App(name="myapp", version="1.0.0")
        tools = App(name="tools", version="2.0.0")

        @tools.command
        def compress(input: Path, output: Path):
            """Compress a file."""
            pass

        app.command(tools, name="*")

        program = program_from_app(app)

        assert program.name == "myapp"
        assert "compress" in program.subcommands
        assert program.subcommands["compress"].name == "myapp compress"
        assert program.subcommands["compress"].version == "2.0.0"
        assert program.subcommands["compress"].description == "Compress a file."

    def test_multiple_subcommands_same_level(self):
        app = App(name="myapp", version="1.0.0")
        remote = App(name="remote", version="2.0.0")

        @remote.command
        def add(input: Path):
            """Add a remote."""
            pass

        @remote.command
        def remove(input: Path):
            """Remove a remote."""
            pass

        app.command(remote)

        program = program_from_app(app)

        assert program.name == "myapp"
        assert "add" in program.subcommands
        assert "remove" in program.subcommands
        assert program.subcommands["add"].name == "myapp remote add"
        assert program.subcommands["remove"].name == "myapp remote remove"

    def test_mixed_nested_and_flattened(self):
        app = App(name="myapp", version="1.0.0")
        group = App(name="group")
        tools = App(name="tools")

        @group.command
        def status():
            """Status command."""
            pass

        @tools.command
        def compress(input: Path):
            """Compress a file."""
            pass

        app.command(group)
        app.command(tools, name="*")

        program = program_from_app(app)

        assert program.name == "myapp"
        assert "status" in program.subcommands
        assert "compress" in program.subcommands
        assert program.subcommands["status"].name == "myapp group status"
        assert program.subcommands["compress"].name == "myapp compress"


class TestArgsVariablePositional:
    def test_star_args_single_file(self, working_tmp_path: Path):
        """Test that *args parameter with INPUT_FILES marker works."""
        input_file_1 = working_tmp_path / "input1.txt"
        input_fn_1 = input_file_1.name
        input_file_2 = working_tmp_path / "input2.txt"
        input_fn_2 = input_file_2.name
        input_file_1.write_text("hello")
        input_file_2.write_text("world")
        output_file = working_tmp_path / "output.txt"
        output_fn = output_file.name
        # TODO use file name in other tests as well

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def myfunc(
            *files: Annotated[tuple[Path, ...], INPUT_FILES],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            # Cyclopts passes *args as tuple of tuples: ((Path1,), (Path2,))
            combined = "\n".join(f[0].read_text().upper() for f in files)
            return output.write_text(combined)

        # TODO fix `WARNING  rocrate_action_recorder.adapters.cyclopts:cyclopts.py:424 Argument name 'files' does not exist in parsed Cyclopts args.`
        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[input_fn_1, input_fn_2, "--output", output_fn],
        )

        assert result == 11
        assert output_file.read_text() == "HELLO\nWORLD"
        assert_crate(
            working_tmp_path,
            expected_input_ids={input_fn_1, input_fn_2},
            expected_output_ids={output_fn},
        )


class TestAsyncCommands:
    def test_async_command_basic(self, working_tmp_path: Path):
        """Test that basic async command recording works."""
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        # TODO if version is not given, use pytest version, always pass version in tests
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        async def myfunc(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            await asyncio.sleep(0)
            output.write_text(input.read_text().upper())
            return 10

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[str(input_file), str(output_file)],
        )

        assert result == 10
        assert output_file.read_text() == "DATA"
        assert_crate(
            working_tmp_path,
            expected_input_ids={"input.txt"},
            expected_output_ids={"output.txt"},
        )

    def test_async_command_with_subcommand(self, working_tmp_path: Path):
        """Test that async subcommands work correctly."""
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.command
        async def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            await asyncio.sleep(0)
            output.write_text(input.read_text().upper())
            return 10

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["process", str(input_file), str(output_file)],
        )

        assert result == 10
        assert output_file.read_text() == "DATA"
        assert_crate(
            working_tmp_path,
            expected_action_id=f"myapp process {input_file} {output_file}",
            expected_input_ids={"input.txt"},
            expected_output_ids={"output.txt"},
        )

    def test_async_command_with_trigger_on(self, working_tmp_path: Path):
        """Test that RECORD_TRIGGER works with async commands when trigger is True."""
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        async def myfunc(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            prov: Annotated[bool, RECORD_TRIGGER] = False,
        ):
            await asyncio.sleep(0)
            output.write_text(input.read_text().upper())
            return 10

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["--prov", str(input_file), str(output_file)],
        )

        assert result == 10
        assert output_file.read_text() == "DATA"
        assert (working_tmp_path / "ro-crate-metadata.json").exists()

    def test_async_command_with_trigger_off(self, working_tmp_path: Path):
        """Test that RECORD_TRIGGER works with async commands when trigger is False."""
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        async def myfunc(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            prov: Annotated[bool, RECORD_TRIGGER] = False,
        ):
            await asyncio.sleep(0)
            output.write_text(input.read_text().upper())
            return 10

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[str(input_file), str(output_file)],
        )

        assert result == 10
        assert output_file.read_text() == "DATA"
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()


class TestMetaApp:
    def test_meta_app_with_record_trigger_at_meta_level(self, working_tmp_path: Path):
        """Test meta app with RECORD_TRIGGER in meta command parameters.

        When using meta apps, the trigger flag is parsed by the meta app,
        which then forwards the appropriate tokens to the parent command.
        This test demonstrates the meta app pattern where the meta command
        can conditionally add flags to the forwarded tokens.
        """
        from cyclopts import Parameter

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            prov: Annotated[bool, RECORD_TRIGGER] = False,
        ):
            output.write_text(input.read_text().upper())
            return 4

        @app.meta.default
        def meta(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
            prov: Annotated[bool, RECORD_TRIGGER] = False,
        ):
            tokens_list = list(tokens)
            if prov:
                tokens_list.append("--prov")
            app(tokens_list)

        # With trigger off (prov=False, default)
        # The meta app receives tokens without --prov, so it doesn't add it
        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[str(input_file), str(output_file)],
        )
        assert result == 4
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()

        # With trigger on (prov=True)
        # The meta app receives --prov, adds it to tokens, and the inner command
        # sees it and triggers recording
        run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["--prov", str(input_file), str(output_file)],
        )
        assert (working_tmp_path / "ro-crate-metadata.json").exists()

    def test_meta_app_with_record_trigger_at_inner_command_level(
        self, working_tmp_path: Path
    ):
        """Test meta app with RECORD_TRIGGER in inner command."""
        from cyclopts import Parameter

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            prov: Annotated[bool, RECORD_TRIGGER] = False,
        ):
            output.write_text(input.read_text().upper())
            return 4

        @app.meta.default
        def meta(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
        ):
            app(tokens)

        # With trigger off
        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[str(input_file), str(output_file)],
        )
        assert result == 4
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()

        # With trigger on
        run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["--prov", str(input_file), str(output_file)],
        )
        assert (working_tmp_path / "ro-crate-metadata.json").exists()

    def test_meta_app_with_subcommand(self, working_tmp_path: Path):
        """Test meta app wrapping subcommands."""

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.command
        def process(
            input: Annotated[Path, INPUT_FILE], output: Annotated[Path, OUTPUT_FILE]
        ):
            output.write_text(input.read_text().upper())
            return 4

        @app.meta.default
        def meta(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
        ):
            app(tokens)

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["process", str(input_file), str(output_file)],
        )

        assert result == 4
        assert output_file.read_text() == "DATA"
        assert_crate(
            working_tmp_path,
            expected_action_id=f"myapp process {input_file} {output_file}",
            expected_input_ids={"input.txt"},
            expected_output_ids={"output.txt"},
        )

    def test_meta_app_with_subcommand_and_trigger(self, working_tmp_path: Path):
        """Test meta app with subcommand that has RECORD_TRIGGER."""
        # Remove inner imports
        from cyclopts import Parameter

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.command
        def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            prov: Annotated[bool, RECORD_TRIGGER] = False,
        ):
            output.write_text(input.read_text().upper())
            return 4

        @app.meta.default
        def meta(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
        ):
            app(tokens)

        # With trigger off
        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["process", str(input_file), str(output_file)],
        )
        assert result == 4
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()

        # With trigger on
        run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["process", "--prov", str(input_file), str(output_file)],
        )
        assert (working_tmp_path / "ro-crate-metadata.json").exists()

    def test_meta_app_nested_meta(self, working_tmp_path: Path):
        """Test nested meta apps (meta of meta)."""
        from cyclopts import Parameter

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = working_tmp_path / "output.txt"

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def process(
            input: Annotated[Path, INPUT_FILE], output: Annotated[Path, OUTPUT_FILE]
        ):
            output.write_text(input.read_text().upper())
            return 4

        @app.meta.default
        def meta(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
        ):
            app(tokens)

        @app.meta.meta.default
        def meta_meta(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
        ):
            app.meta(tokens)

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=[str(input_file), str(output_file)],
        )

        assert result == 4
        assert output_file.read_text() == "DATA"
        assert_crate(
            working_tmp_path,
            expected_input_ids={"input.txt"},
            expected_output_ids={"output.txt"},
        )

    def test_meta_app_with_meta_own_command(self, working_tmp_path: Path):
        """Test meta app with its own command that doesn't call parent."""
        from cyclopts import Parameter

        output_file = working_tmp_path / "output.txt"

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def process(
            input: Annotated[Path, INPUT_FILE], output: Annotated[Path, OUTPUT_FILE]
        ):
            output.write_text(input.read_text().upper())
            return 4

        @app.meta.command
        def info(output: Annotated[Path, OUTPUT_FILE]):
            """Print info and write to output."""
            output.write_text("info output")
            return 11

        @app.meta.default
        def meta(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
        ):
            app(tokens)

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["info", str(output_file)],
        )

        assert result == 11
        assert output_file.read_text() == "info output"
        assert_crate(
            working_tmp_path,
            expected_output_ids={"output.txt"},
        )


class TestHelpVersionCommands:
    """Test that help and version commands work without IO markers."""

    def test_help_flag_does_not_record(self, working_tmp_path: Path):
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("hello")

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def myfunc(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            return output.write_text(input.read_text().upper())

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["--help"],
        )

        assert result is None or result == 0
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()

    def test_version_flag_does_not_record(self, working_tmp_path: Path):
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("hello")

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def myfunc(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            return output.write_text(input.read_text().upper())

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["--version"],
        )

        assert result is None or result == 0
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()

    def test_subcommand_help_does_not_record(self, working_tmp_path: Path):
        input_file = working_tmp_path / "input.txt"
        input_file.write_text("hello")

        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.command
        def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            """Process files."""
            return output.write_text(input.read_text().upper())

        result = run_with_record(
            app,
            dataset_license="CC-BY-4.0",
            tokens=["process", "--help"],
        )

        assert result is None or result == 0
        assert not (working_tmp_path / "ro-crate-metadata.json").exists()


class Test_cyclopts_value2paths:
    def test_single_path(self, tmp_path: Path):
        path = tmp_path / "test.txt"
        path.write_text("test")

        paths = cyclopts_value2paths(path)

        assert paths == [path]

    def test_list_of_paths(self, tmp_path: Path):
        path1 = tmp_path / "test1.txt"
        path2 = tmp_path / "test2.txt"
        path1.write_text("test1")
        path2.write_text("test2")

        paths = cyclopts_value2paths([path1, path2])

        assert paths == [path1, path2]

    def test_duplicate_paths(self, tmp_path: Path):
        path = tmp_path / "test.txt"
        path.write_text("test")

        paths = cyclopts_value2paths([path, path])

        assert paths == [path]

    def test_stdiopath_dash_ignored(self, caplog: pytest.LogCaptureFixture):
        paths = cyclopts_value2paths(StdioPath("-"))

        assert paths == []
        assert (
            "Unable to convert stdin/stdout file-like object to Path, ignoring it"
            in caplog.text
        )

    def test_mixed_paths_with_stdiopath_dash(self, tmp_path: Path):
        path = tmp_path / "input.txt"

        paths = cyclopts_value2paths([path, StdioPath("-")])

        assert paths == [path]
