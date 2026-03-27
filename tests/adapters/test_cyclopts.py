from dataclasses import dataclass
import json
from pathlib import Path
from typing import Annotated

import pytest
import rocrate_action_recorder.adapters.cyclopts as cyclopts_adapter

from cyclopts import App, Parameter
from cyclopts.types import StdioPath
from rocrate_action_recorder.adapters.cyclopts import (
    INPUT_FILE,
    OUTPUT_FILE,
    RECORD_TRIGGER,
    cyclopts_value2paths,
    run_with_record,
)


class TestRunWithRecord:
    def test_single_input_output_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)

        input_file = tmp_path / "input.txt"
        input_file.write_text("hello")
        output_file = tmp_path / "output.txt"

        app = App(version="1.0.0")

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
        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()

    @pytest.fixture
    def app_with_record_trigger(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)

        app = App(version="1.0.0")

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
        self, tmp_path: Path, app_with_record_trigger: App
    ):
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello")
        output_file = tmp_path / "output.txt"

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app_with_record_trigger,
                dataset_license="CC-BY-4.0",
                tokens=[str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 5
        assert output_file.read_text() == "HELLO"
        assert not (tmp_path / "ro-crate-metadata.json").exists()

    def test_record_trigger_on(self, tmp_path: Path, app_with_record_trigger: App):
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello")
        output_file = tmp_path / "output.txt"

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app_with_record_trigger,
                dataset_license="CC-BY-4.0",
                tokens=["--prov", str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 5
        assert output_file.read_text() == "HELLO"
        assert (tmp_path / "ro-crate-metadata.json").exists()

    def test_single_argument_collection_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        app = App(version="1.0.0")

        @app.default
        def myfunc():
            return None

        captured: dict[str, int] = {}

        def fake_detect_ios_and_trigger(argument_collection):
            captured["detect"] = id(argument_collection)
            return cyclopts_adapter.IOArgumentNames(), None

        def fake_record_cyclopts(**kwargs):
            captured["record"] = id(kwargs["argument_collection"])
            return tmp_path / "ro-crate-metadata.json"

        monkeypatch.setattr(
            cyclopts_adapter, "_detect_ios_and_trigger", fake_detect_ios_and_trigger
        )
        monkeypatch.setattr(cyclopts_adapter, "record_cyclopts", fake_record_cyclopts)

        with pytest.raises(SystemExit):
            run_with_record(app, tokens=[])

        assert captured["detect"] == captured["record"]

    def test_stdiopath_dash_not_recorded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ):
        monkeypatch.chdir(tmp_path)

        output_file = tmp_path / "output.txt"

        app = App(version="1.0.0")

        @app.default
        def myfunc(
            input: Annotated[StdioPath, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            return output.write_text("from stdin")

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["-", str(output_file)],
            )

        assert exc_info.value.code == 10
        assert output_file.read_text() == "from stdin"

        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()

        graph = {e["@id"]: e for e in json.loads(crate_path.read_text())["@graph"]}
        action = next(e for e in graph.values() if e.get("@type") == "CreateAction")
        input_ids = {o["@id"] for o in action.get("object", [])}
        output_ids = {r["@id"] for r in action.get("result", [])}

        assert "-" not in input_ids
        assert "output.txt" in output_ids
        assert (
            "Unable to convert stdin/stdout file-like object to Path, ignoring it"
            in caplog.text
        )
        assert "has no associated path-like argument value(s)." in caplog.text


class TestRunWithRecordSingleLevelSubcommand:
    def test_subcommand_single_level(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        app = App(name="myapp")

        @app.command
        def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            "Process files."
            output.write_text(input.read_text().upper())

        @app.command
        def validate(schema: Annotated[Path, INPUT_FILE]):
            "Validate files."
            pass

        with pytest.raises(SystemExit):
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", str(input_file), str(output_file)],
            )

        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()
        graph = {e["@id"]: e for e in json.loads(crate_path.read_text())["@graph"]}

        action = next(e for e in graph.values() if e.get("@type") == "CreateAction")
        expected_action_id = f"process {input_file} {output_file}"
        assert action["@id"] == expected_action_id
        assert action["name"] == expected_action_id
        input_ids = {o["@id"] for o in action.get("object", [])}
        output_ids = {r["@id"] for r in action.get("result", [])}
        assert "input.txt" in input_ids
        assert "output.txt" in output_ids
        assert not any("schema" in eid for eid in graph)

    def test_subcommand_with_trigger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        app = App(name="myapp")

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

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", "--prov", str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 4
        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()
        assert output_file.read_text() == "DATA"
        graph = {e["@id"]: e for e in json.loads(crate_path.read_text())["@graph"]}

        action = next(e for e in graph.values() if e.get("@type") == "CreateAction")
        expected_action_id = f"process --prov {input_file} {output_file}"
        assert action["@id"] == expected_action_id
        assert action["name"] == expected_action_id
        input_ids = {o["@id"] for o in action.get("object", [])}
        output_ids = {r["@id"] for r in action.get("result", [])}
        assert "input.txt" in input_ids
        assert "output.txt" in output_ids

    def test_subcommand_with_trigger_in_dataclass_on(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        @Parameter(name="*")
        @dataclass
        class Common:
            prov: Annotated[bool, RECORD_TRIGGER] = False

        app = App(name="myapp")

        @app.command
        def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            common: Common | None = None,
        ):
            "Process files."
            print(common)
            output.write_text(input.read_text().upper())
            return output.stat().st_size

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", "--prov", str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 4
        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()

    def test_subcommand_with_trigger_in_dataclass_off(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        @Parameter(name="*")
        @dataclass
        class Common:
            prov: Annotated[bool, RECORD_TRIGGER] = False

        app = App(name="myapp")

        @app.command
        def process(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            common: Common | None = None,
        ):
            "Process files."
            print(common)
            output.write_text(input.read_text().upper())
            return output.stat().st_size

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["process", str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 4
        crate_path = tmp_path / "ro-crate-metadata.json"
        assert not crate_path.exists()


class TestRunWithRecordTwoLevelSubcommand:
    def test_subcommand_two_levels(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        app = App(name="myapp")
        remote = App(name="remote")

        @remote.command
        def add(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
        ):
            "Add a remote."
            output.write_text(input.read_text().upper())

        @remote.command
        def remove(schema: Annotated[Path, INPUT_FILE]):
            "Remove a remote."
            pass

        app.command(remote)

        with pytest.raises(SystemExit):
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", str(input_file), str(output_file)],
            )

        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()
        graph = {e["@id"]: e for e in json.loads(crate_path.read_text())["@graph"]}

        action = next(e for e in graph.values() if e.get("@type") == "CreateAction")
        expected_action_id = f"remote add {input_file} {output_file}"
        assert action["@id"] == expected_action_id
        assert action["name"] == expected_action_id
        input_ids = {o["@id"] for o in action.get("object", [])}
        output_ids = {r["@id"] for r in action.get("result", [])}
        assert "input.txt" in input_ids
        assert "output.txt" in output_ids
        assert not any("schema" in eid for eid in graph)

    def test_subcommand_two_levels_with_trigger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        app = App(name="myapp")
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

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", "--prov", str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 4
        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()
        assert output_file.read_text() == "DATA"
        graph = {e["@id"]: e for e in json.loads(crate_path.read_text())["@graph"]}

        action = next(e for e in graph.values() if e.get("@type") == "CreateAction")
        expected_action_id = f"remote add --prov {input_file} {output_file}"
        assert action["@id"] == expected_action_id
        assert action["name"] == expected_action_id
        input_ids = {o["@id"] for o in action.get("object", [])}
        output_ids = {r["@id"] for r in action.get("result", [])}
        assert "input.txt" in input_ids
        assert "output.txt" in output_ids

    def test_subcommand_two_levels_with_trigger_in_dataclass_on(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        @Parameter(name="*")
        @dataclass
        class Common:
            prov: Annotated[bool, RECORD_TRIGGER] = False

        app = App(name="myapp")
        remote = App(name="remote")

        @remote.command
        def add(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            common: Common | None = None,
        ):
            "Add a remote."
            print(common)
            output.write_text(input.read_text().upper())
            return output.stat().st_size

        app.command(remote)

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", "--prov", str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 4
        crate_path = tmp_path / "ro-crate-metadata.json"
        assert crate_path.exists()

    def test_subcommand_two_levels_with_trigger_in_dataclass_off(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        input_file = tmp_path / "input.txt"
        input_file.write_text("data")
        output_file = tmp_path / "output.txt"

        @Parameter(name="*")
        @dataclass
        class Common:
            prov: Annotated[bool, RECORD_TRIGGER] = False

        app = App(name="myapp")
        remote = App(name="remote")

        @remote.command
        def add(
            input: Annotated[Path, INPUT_FILE],
            output: Annotated[Path, OUTPUT_FILE],
            *,
            common: Common | None = None,
        ):
            "Add a remote."
            print(common)
            output.write_text(input.read_text().upper())
            return output.stat().st_size

        app.command(remote)

        with pytest.raises(SystemExit) as exc_info:
            run_with_record(
                app,
                dataset_license="CC-BY-4.0",
                tokens=["remote", "add", str(input_file), str(output_file)],
            )

        assert exc_info.value.code == 4
        crate_path = tmp_path / "ro-crate-metadata.json"
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
