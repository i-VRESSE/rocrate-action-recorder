from dataclasses import dataclass
import json
from pathlib import Path
from typing import Annotated, Any, cast

import pytest

from cyclopts import App, Parameter
from cyclopts.types import StdioPath
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
    cyclopts_value2paths,
    run_with_record,
)


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
            crate_path = working_tmp_path / "ro-crate-metadata.json"
            assert crate_path.exists()

        def test_multiple_input_files(self, working_tmp_path: Path):
            input_file_1 = working_tmp_path / "input1.txt"
            input_file_2 = working_tmp_path / "input2.txt"
            input_file_1.write_text("hello")
            input_file_2.write_text("world")
            output_file = working_tmp_path / "output.txt"

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
                    str(input_file_1),
                    "--input-files",
                    str(input_file_2),
                    "--output",
                    str(output_file),
                ],
            )

            assert result == 11
            assert output_file.read_text() == "HELLO\nWORLD"
            assert_crate(
                working_tmp_path,
                expected_input_ids={"input1.txt", "input2.txt"},
            )

        def test_multiple_output_files(self, working_tmp_path: Path):
            input_file = working_tmp_path / "input.txt"
            input_file.write_text("hello")
            output_file_1 = working_tmp_path / "output1.txt"
            output_file_2 = working_tmp_path / "output2.txt"

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
                    str(input_file),
                    "--output-files",
                    str(output_file_1),
                    "--output-files",
                    str(output_file_2),
                ],
            )

            assert result == 10
            assert output_file_1.read_text() == "HELLO"
            assert output_file_2.read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
                expected_output_ids={"output1.txt", "output2.txt"},
            )

        def test_single_input_output_dir(self, working_tmp_path: Path):
            input_dir = working_tmp_path / "input"
            input_dir.mkdir()
            (input_dir / "a.txt").write_text("hello")
            output_dir = working_tmp_path / "output"

            app = App(result_action="return_value", version="1.0.0")

            @app.default
            def myfunc(
                input_dir_arg: Annotated[Path, INPUT_DIR],
                output_dir_arg: Annotated[Path, OUTPUT_DIR],
            ):
                output_dir_arg.mkdir()
                content = (input_dir_arg / "a.txt").read_text().upper()
                return (output_dir_arg / "a.txt").write_text(content)

            result = run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=[str(input_dir), str(output_dir)],
            )

            assert result == 5
            assert (output_dir / "a.txt").read_text() == "HELLO"
            assert_crate(
                working_tmp_path,
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

            expected_action_id = f"process {input_file} {output_file}"
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
            expected_action_id = f"process --prov {input_file} {output_file}"
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

            expected_action_id = f"remote add {input_file} {output_file}"
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
            expected_action_id = f"remote add --prov {input_file} {output_file}"
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
