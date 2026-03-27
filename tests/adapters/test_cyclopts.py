from pathlib import Path

import pytest

from typing import Annotated

from cyclopts import App
from rocrate_action_recorder.adapters.cyclopts import (
    INPUT_FILE,
    OUTPUT_FILE,
    RECORD_TRIGGER,
    cyclopts_value2paths,
    run_with_record,
    try_convert_to_path,
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


class Test_try_convert_to_path:
    def test_path_object(self, tmp_path: Path):
        path = tmp_path / "test.txt"

        result = try_convert_to_path(path)

        assert result == path

    def test_string_path(self, tmp_path: Path):
        path = tmp_path / "test.txt"

        result = try_convert_to_path(str(path))

        assert result == path

    def test_none(self):
        result = try_convert_to_path(None)

        assert result is None
