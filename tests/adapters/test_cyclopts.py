import asyncio
from io import BytesIO, TextIOWrapper
from textwrap import dedent
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from attrs import define
import pytest
from cyclopts import App, Group, MissingArgumentError, Parameter
from cyclopts.types import (
    NonExistentFile,
    StdioPath,
    ExistingDirectory,
    NonExistentDirectory,
)
from pydantic import BaseModel
from rocrate.rocrate import Metadata, ROCrate

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
    record_cyclopts,
)
from rocrate_action_recorder.adapters.shared import value2paths as value2paths


def assert_no_crate(crate_dir: Path):
    crate_path = crate_dir / Metadata.BASENAME
    assert not crate_path.exists()


def assert_crate(
    crate_dir: Path,
    *,
    action_id: str | None = None,
    input_ids: set[str] | None = None,
    output_ids: set[str] | None = None,
    instrument_id: str | None = None,
) -> tuple[ROCrate, dict]:
    crate_path = crate_dir / Metadata.BASENAME
    assert crate_path.exists()

    print(crate_path.read_text())
    crate = ROCrate(crate_dir)
    actions = crate.get_by_type("CreateAction", exact=True)
    assert len(actions) == 1, (
        f"Expected exactly one CreateAction in the crate, found {len(actions)}"
    )
    action = actions[0]

    if action_id is not None:
        assert action["@id"] == action_id
        assert action["name"] == action_id
    if instrument_id is not None:
        assert action["instrument"]["@id"] == instrument_id

    input_ids = {i["@id"] for i in action.get("object", [])}
    if input_ids is not None:
        assert input_ids <= input_ids

    output_ids = {o["@id"] for o in action.get("result", [])}
    if output_ids is not None:
        assert output_ids <= output_ids

    return crate, action


@pytest.fixture
def working_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestMarkerless:
    def app_with_no_markers(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def main():
            pass

        return app

    def test_help(self, working_tmp_path: Path):
        app = self.app_with_no_markers()

        with record_cyclopts(app, tokens=["--help"]):
            app(tokens=["--help"])

        assert_no_crate(working_tmp_path)

    def test_version(self, working_tmp_path: Path):
        app = self.app_with_no_markers()

        with record_cyclopts(app, tokens=["--version"]):
            app(tokens=["--version"])

        assert_no_crate(working_tmp_path)

    def test_noargs(self, working_tmp_path: Path):
        app = App(
            result_action="return_value",
            version="1.0.0",
            exit_on_error=False,
            help_on_error=True,
        )

        @app.default
        def main(something: str):
            pass

        with pytest.raises(MissingArgumentError):
            with record_cyclopts(app, tokens=""):
                app(tokens="")

        assert_no_crate(working_tmp_path)

    def test_simplest(self, working_tmp_path: Path, caplog: pytest.LogCaptureFixture):
        app = self.app_with_no_markers()
        # need to supply tokens otherwise sys.argv is used
        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id="main",
            input_ids=set(),
            output_ids=set(),
            instrument_id="main@1.0.0",
        )
        assert "No dataset license specified for the RO-Crate" in caplog.text

    def test_description_from_app(self, working_tmp_path: Path):
        app = self.app_with_no_markers()
        app.help = "This is the help message for the app."
        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
        )
        instrument = action["instrument"]
        assert instrument["description"] == "This is the help message for the app."

    def test_description_from_docstring(self, working_tmp_path: Path):
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def main():
            """This is the docstring for the main function."""
            pass

        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
        )
        instrument = action["instrument"]
        assert (
            instrument["description"] == "This is the docstring for the main function."
        )

    def test_description_from_docstring_head_only(self, working_tmp_path: Path):
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def main():
            """This is the docstring for the main function.

            Some more text that should be included.

            Returns:
                Nothing
            """
            pass

        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
        )
        instrument = action["instrument"]
        expected = dedent("""\
            This is the docstring for the main function.

            Some more text that should be included.""")
        assert instrument["description"] == expected

    def test_override_dataset_license(
        self, working_tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        app = self.app_with_no_markers()
        tokens = ""

        with record_cyclopts(app, dataset_license="CC-BY-4.0", tokens=tokens):
            app(tokens=tokens)

        crate, _ = assert_crate(working_tmp_path, action_id="main")
        assert crate.license == "CC-BY-4.0"
        assert "No dataset license specified for the RO-Crate" not in caplog.text

    def test_override_crate_dir(self, working_tmp_path: Path):
        crate_dir = working_tmp_path / "mycrate"
        crate_dir.mkdir()
        app = self.app_with_no_markers()
        tokens = ""

        with record_cyclopts(app, tokens=tokens, crate_dir=crate_dir):
            app(tokens=tokens)

        assert_crate(crate_dir, action_id="main")

    def test_override_software_version(self, working_tmp_path: Path):
        app = self.app_with_no_markers()
        tokens = ""

        with record_cyclopts(app, software_version="2.0.0", tokens=tokens):
            app(tokens=tokens)

        assert_crate(
            working_tmp_path,
            action_id="main",
            instrument_id="main@2.0.0",
        )

    def test_override_user(self, working_tmp_path: Path):
        app = self.app_with_no_markers()
        tokens = ""

        with record_cyclopts(app, current_user="alice", tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(working_tmp_path, action_id="main")
        assert action["agent"]["@id"] == "alice"


class TestTrigger:
    def app_with_parameterless_trigger(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def main(
            *,
            prov: Annotated[
                bool,
                RECORD_TRIGGER,
            ] = False,
        ):
            print(f"Provenance recording is {'enabled' if prov else 'disabled'}.")

        return app

    def test_parameterless_on(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_parameterless_trigger()

        tokens = "--prov"
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out
        assert_crate(
            working_tmp_path,
            action_id="main --prov",
            input_ids=set(),
            output_ids=set(),
            instrument_id="main@1.0.0",
        )

    def test_parameterless_off(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_parameterless_trigger()

        tokens = ""
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is disabled." in captured.out
        assert_no_crate(working_tmp_path)

    def app_with_trigger(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def main(
            *,
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False,
        ):
            print(f"Provenance recording is {'enabled' if prov else 'disabled'}.")

        return app

    def test_with_trigger_on(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_trigger()
        tokens = "--prov"

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out
        assert_crate(
            working_tmp_path,
            action_id="main --prov",
            input_ids=set(),
            output_ids=set(),
            instrument_id="main@1.0.0",
        )

    def test_with_trigger_default(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_trigger()
        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is disabled." in captured.out
        assert_no_crate(working_tmp_path)

    def app_with_trigger_in_meta(self) -> App:
        app = App(result_action="return_value")

        app.meta.group_parameters = Group("Session Parameters", sort_key=0)
        app.meta.version = "1.0.0"

        @app.command
        def foo(loops: int):
            for i in range(loops):
                print(f"Looping! {i}")

        @app.meta.default
        def launcher(
            *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False,
        ):
            print(f"Provenance recording is {'enabled' if prov else 'disabled'}.")
            app(tokens)

        return app

    def test_trigger_on_in_meta(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_trigger_in_meta()
        tokens = "--prov foo 3"

        with record_cyclopts(app.meta, tokens=tokens):
            app.meta(tokens=tokens)

        assert_crate(
            working_tmp_path,
            action_id="launcher --prov foo 3",
            input_ids=set(),
            output_ids=set(),
            instrument_id="launcher@1.0.0",
        )
        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out

    def test_trigger_off_in_meta(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_trigger_in_meta()
        tokens = "foo 3"

        with record_cyclopts(app.meta, tokens=tokens):
            app.meta(tokens=tokens)

        assert_no_crate(working_tmp_path)
        captured = capsys.readouterr()
        assert "Provenance recording is disabled." in captured.out

    def app_with_shared_trigger(self):
        app = App(result_action="return_value", version="1.0.0")

        @Parameter(name="*")
        @dataclass
        class Common:
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False

        @app.default
        def main(*, common: Common | None = None):
            print(
                f"Provenance recording is {'enabled' if common and common.prov else 'disabled'}."
            )

        return app

    def test_shared_trigger_on(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_shared_trigger()
        tokens = "--prov"

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out
        assert_crate(
            working_tmp_path,
            action_id="main --prov",
            input_ids=set(),
            output_ids=set(),
            instrument_id="main@1.0.0",
        )

    def test_shared_trigger_off(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_shared_trigger()
        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is disabled." in captured.out
        assert_no_crate(working_tmp_path)

    def app_with_nested_dataclass_trigger(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        @dataclass
        class Common:
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False

        @app.default
        def main(*, common: Common | None = None):
            print(
                f"Provenance recording is {'enabled' if common and common.prov else 'disabled'}."
            )

        return app

    def app_with_nested_basemodel_trigger(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        class Common(BaseModel):
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False

        @app.default
        def main(*, common: Common | None = None):
            print(
                f"Provenance recording is {'enabled' if common and common.prov else 'disabled'}."
            )

        return app

    def app_with_nested_define_trigger(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        @define
        class Common:
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False

        @app.default
        def main(*, common: Common | None = None):
            print(
                f"Provenance recording is {'enabled' if common and common.prov else 'disabled'}."
            )

        return app

    @pytest.mark.parametrize(
        "app_factory",
        [
            app_with_nested_dataclass_trigger,
            app_with_nested_basemodel_trigger,
            app_with_nested_define_trigger,
        ],
        ids=["dataclass", "basemodel", "define"],
    )
    def test_nested_trigger_on(
        self,
        app_factory,
        working_tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ):
        app = app_factory(self)
        tokens = "--common.prov"

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out
        assert_crate(
            working_tmp_path,
            action_id="main --common.prov",
            input_ids=set(),
            output_ids=set(),
            instrument_id="main@1.0.0",
        )

    @pytest.mark.parametrize(
        "app_factory",
        [
            app_with_nested_dataclass_trigger,
            app_with_nested_basemodel_trigger,
            app_with_nested_define_trigger,
        ],
        ids=["dataclass", "basemodel", "define"],
    )
    def test_nested_trigger_off(
        self,
        app_factory,
        working_tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ):
        app = app_factory(self)
        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is disabled." in captured.out
        assert_no_crate(working_tmp_path)

    def app_with_nested_basemodel_output_trigger(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        class Common(BaseModel):
            output: Annotated[Path, OUTPUT_FILE]
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False

        @app.default
        def main(*, common: Common | None = None):
            assert common is not None
            common.output.write_text("DATA")
            print(
                f"Provenance recording is {'enabled' if common.prov else 'disabled'}."
            )

        return app

    def test_nested_basemodel_output_trigger_on(
        self,
        working_tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ):
        app = self.app_with_nested_basemodel_output_trigger()
        tokens = ["--common.prov", "--common.output", "output.txt"]

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out
        assert (working_tmp_path / "output.txt").read_text() == "DATA"
        assert_crate(
            working_tmp_path,
            action_id="main --common.prov --common.output output.txt",
            input_ids=set(),
            output_ids={"output.txt"},
            instrument_id="main@1.0.0",
        )


class TestSubcommands:
    def app_with_subcommand(self) -> App:
        app = App(
            name="myapp",
            result_action="return_value",
            version="1.0.0",
            help="This is my app.",
        )

        @app.command
        def process():
            """Process some data.

            Some more description of the process command.

            Raises:
                ValueError: If something goes wrong.
            """
            print("was here")

        return app

    def test_subcommand(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_subcommand()
        tokens = "process"

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "was here" in captured.out
        _, action = assert_crate(
            working_tmp_path,
            action_id="myapp process",
            input_ids=set(),
            output_ids=set(),
            instrument_id="myapp@1.0.0",
        )
        instrument = action["instrument"]
        assert instrument["description"] == "This is my app."

    def app_with_subsubcommand(self) -> App:
        app = App(name="myapp", result_action="return_value", version="1.0.0")
        remote = App(name="remote")
        app.command(remote)

        @remote.command
        def add():
            print("added remote")

        return app

    def test_subsubcommand(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_subsubcommand()
        tokens = "remote add"

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "added remote" in captured.out
        assert_crate(
            working_tmp_path,
            action_id="myapp remote add",
            input_ids=set(),
            output_ids=set(),
            instrument_id="myapp@1.0.0",
        )


class TestSubCommandWithTrigger:
    def app_with_subcommand_trigger(self) -> App:
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.command
        def add(
            *,
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False,
        ):
            print(f"Provenance recording is {'enabled' if prov else 'disabled'}.")

        return app

    def test_on(self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        app = self.app_with_subcommand_trigger()
        tokens = "add --prov"
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out
        assert_crate(
            working_tmp_path,
            action_id="myapp add --prov",
            input_ids=set(),
            output_ids=set(),
            instrument_id="myapp@1.0.0",
        )

    def test_off(self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        app = self.app_with_subcommand_trigger()
        tokens = "add"

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is disabled." in captured.out
        assert_no_crate(working_tmp_path)


class TestSubSubCommandWithTrigger:
    def app_with_subsubcommand_trigger(self) -> App:
        app = App(name="myapp", result_action="return_value", version="1.0.0")
        remote = App(name="remote")
        app.command(remote)

        @remote.command
        def add(
            *,
            prov: Annotated[
                bool,
                Parameter(negative=""),
                RECORD_TRIGGER,
            ] = False,
        ):
            print(f"Provenance recording is {'enabled' if prov else 'disabled'}.")

        return app

    def test_on(self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        app = self.app_with_subsubcommand_trigger()
        tokens = "remote add --prov"
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is enabled." in captured.out
        assert_crate(
            working_tmp_path,
            action_id="myapp remote add --prov",
            input_ids=set(),
            output_ids=set(),
            instrument_id="myapp@1.0.0",
        )

    def test_off(self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        app = self.app_with_subsubcommand_trigger()
        tokens = "remote add"

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Provenance recording is disabled." in captured.out
        assert_no_crate(working_tmp_path)


class TestSingleMarkers:
    def test_input_file_description_from_parameter(self, working_tmp_path: Path):
        app = App(
            name="myapp",
            result_action="return_value",
            version="1.0.0",
            help="The main function",
        )

        @app.default
        def main(
            input: Annotated[
                StdioPath, Parameter(help="The input file path"), INPUT_FILE
            ],
            /,
        ):
            print(f"Received input from {input}.")

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("hello")
        input_fn = input_file.name
        tokens = [input_fn]

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp {input_fn}",
            input_ids={input_fn},
            output_ids=set(),
            instrument_id="myapp@1.0.0",
        )
        instrument = action["instrument"]
        assert instrument["description"] == "The main function"
        # Check input file properties
        f = action["object"][0]
        assert f.id == input_fn
        assert f["description"] == "The input file path"
        assert f["name"] == input_fn

    def test_input_file_description_from_docstring(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(input: Annotated[StdioPath, INPUT_FILE], /):
            """The main function

            Args:
                input: The input file path
            """
            print(f"Received input from {input}.")

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("hello")
        input_fn = input_file.name
        tokens = [input_fn]

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp {input_fn}",
            input_ids={input_fn},
            output_ids=set(),
            instrument_id="myapp@1.0.0",
        )
        instrument = action["instrument"]
        assert instrument["description"] == "The main function"
        # Check input file properties
        f = action["object"][0]
        assert f.id == input_fn
        assert f["description"] == "The input file path"
        assert f["name"] == input_fn

    def test_input_file_in_nested_tuple(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(*, input: Annotated[tuple[tuple[int, StdioPath], int], INPUT_FILE]):
            print(f"Received input from {input}.")

        input_file = working_tmp_path / "input.txt"
        input_file.write_text("hello")
        input_fn = input_file.name
        tokens = ["--input", "42", input_fn, "69"]

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp --input 42 {input_fn} 69",
            input_ids={input_fn},
            output_ids=set(),
            instrument_id="myapp@1.0.0",
        )
        # Check input file properties
        f = action["object"][0]
        assert f.id == input_fn
        assert f["description"] == ""
        assert f["name"] == input_fn

    def test_output_file(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(output: Annotated[NonExistentFile, OUTPUT_FILE], /):
            """Write something to the output file.

            Args:
                output: The output file path
            """
            output.write_text("hello")
            print(f"Wrote output to {output}.")

        print(list(working_tmp_path.iterdir()))
        output_file = working_tmp_path / "output.txt"
        output_fn = output_file.name
        tokens = [output_fn]

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        assert "hello" == output_file.read_text()
        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp {output_fn}",
            input_ids=set(),
            output_ids={output_fn},
        )
        f = action["result"][0]
        assert f.id == output_fn
        assert f["description"] == "The output file path"
        assert f["name"] == output_fn

    def test_input_dir(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(input_dir: Annotated[ExistingDirectory, INPUT_DIR], /):
            """Read something from the input directory.

            Args:
                input_dir: The input directory path
            """
            listing = list(input_dir.iterdir())
            print(f"Read from {input_dir}: {listing}")

        input_dir = working_tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "a.txt").write_text("hello")
        input_fn = input_dir.name
        tokens = [input_fn]

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp {input_fn}",
            # to distinguish dir from file, a / is appended
            input_ids={"input/"},
            output_ids=set(),
        )
        f = action["object"][0]
        assert f.id == "input/"
        assert f["name"] == "input"
        assert f["description"] == "The input directory path"

    def test_output_dir(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(output_dir: Annotated[NonExistentDirectory, OUTPUT_DIR], /):
            """Write something to the output directory.

            Args:
                output_dir: The output directory path
            """
            output_dir.mkdir()
            (output_dir / "result.txt").write_text("hello")
            print(f"Wrote to {output_dir}.")

        output_dir = working_tmp_path / "output"
        output_fn = output_dir.name
        tokens = [output_fn]

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        assert (output_dir / "result.txt").read_text() == "hello"
        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp {output_fn}",
            input_ids=set(),
            output_ids={"output/"},
        )
        f = action["result"][0]
        assert f.id == "output/"
        assert f["name"] == "output"
        assert f["description"] == "The output directory path"


class TestPluralMarkers:
    def test_multiple_input_files_positional_list(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(input_files: Annotated[list[Path], INPUT_FILES], /):
            """Read something from the input files.

            Args:
                input_files: The input file paths
            """
            print(f"Received input files: {input_files}.")

        input_file_1 = working_tmp_path / "input1.txt"
        input_file_2 = working_tmp_path / "input2.txt"
        input_file_1.write_text("hello")
        input_file_2.write_text("world")
        input_fn1 = input_file_1.name
        input_fn2 = input_file_2.name

        tokens = [input_fn1, input_fn2]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp {input_fn1} {input_fn2}",
            input_ids={input_fn1, input_fn2},
            output_ids=set(),
        )
        inputs = action["object"]
        assert len(inputs) == 2
        input1 = inputs[0]
        assert input1.id == input_fn1
        assert input1["name"] == input_fn1
        assert input1["description"] == "The input file paths"
        input2 = inputs[1]
        assert input2.id == input_fn2
        assert input2["name"] == input_fn2
        assert input2["description"] == "The input file paths"

    def test_multiple_input_files_varpos_list(self, working_tmp_path: Path):
        # https://cyclopts.readthedocs.io/en/stable/args_and_kwargs.html#args-variable-positional
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(*input_files: Annotated[Path, INPUT_FILES]):
            """Read something from the input files.

            Args:
                input_files: The input file paths
            """
            print(f"Received input files: {input_files}.")

        input_file_1 = working_tmp_path / "input1.txt"
        input_file_2 = working_tmp_path / "input2.txt"
        input_file_1.write_text("hello")
        input_file_2.write_text("world")
        input_fn1 = input_file_1.name
        input_fn2 = input_file_2.name

        tokens = [input_fn1, input_fn2]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp {input_fn1} {input_fn2}",
            input_ids={input_fn1, input_fn2},
            output_ids=set(),
        )
        inputs = action["object"]
        assert len(inputs) == 2
        input1 = inputs[0]
        assert input1.id == input_fn1
        assert input1["name"] == input_fn1
        assert input1["description"] == "The input file paths"
        input2 = inputs[1]
        assert input2.id == input_fn2
        assert input2["name"] == input_fn2
        assert input2["description"] == "The input file paths"

    def test_multiple_input_files_named_tuple(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(*, foo: Annotated[tuple[Path, int, Path], INPUT_FILES]):
            """Read something from the input files.

            Args:
                foo: The 2 input file paths and an integer in between
            """
            print(f"Received input files: {foo}.")

        input_file_1 = working_tmp_path / "input1.txt"
        input_file_2 = working_tmp_path / "input2.txt"
        input_file_1.write_text("hello")
        input_file_2.write_text("world")
        input_fn1 = input_file_1.name
        input_fn2 = input_file_2.name

        tokens = ["--foo", input_fn1, "42", input_fn2]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp --foo {input_fn1} 42 {input_fn2}",
            input_ids={input_fn1, input_fn2},
            output_ids=set(),
        )
        inputs = action["object"]
        assert len(inputs) == 2
        input1 = inputs[0]
        assert input1.id == input_fn1
        assert input1["name"] == input_fn1
        # description does make sense in this case, since parameter has non-path-like types
        assert (
            input1["description"] == "The 2 input file paths and an integer in between"
        )
        input2 = inputs[1]
        assert input2.id == input_fn2
        assert input2["name"] == input_fn2
        assert (
            input2["description"] == "The 2 input file paths and an integer in between"
        )

    def test_multiple_input_files_named_nested_tuple(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(
            *, foo: Annotated[tuple[tuple[Path, int], tuple[Path, int]], INPUT_FILES]
        ):
            print(f"Received input files: {foo}.")

        input_file_1 = working_tmp_path / "input1.txt"
        input_file_2 = working_tmp_path / "input2.txt"
        input_file_1.write_text("hello")
        input_file_2.write_text("world")
        input_fn1 = input_file_1.name
        input_fn2 = input_file_2.name

        tokens = ["--foo", input_fn1, "42", input_fn2, "69"]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp --foo {input_fn1} 42 {input_fn2} 69",
            input_ids={input_fn1, input_fn2},
            output_ids=set(),
        )
        inputs = action["object"]
        assert len(inputs) == 2
        input1 = inputs[0]
        assert input1.id == input_fn1
        assert input1["name"] == input_fn1
        assert input1["description"] == ""
        input2 = inputs[1]
        assert input2.id == input_fn2
        assert input2["name"] == input_fn2
        assert input2["description"] == ""

    def test_other_plural_markers_as_flags(self, working_tmp_path: Path):
        app = App(name="myapp", result_action="return_value", version="1.0.0")

        @app.default
        def main(
            *,
            input_dirs: Annotated[list[ExistingDirectory], INPUT_DIRS],
            output_files: Annotated[list[NonExistentFile], OUTPUT_FILES],
            output_dirs: Annotated[list[NonExistentDirectory], OUTPUT_DIRS],
        ):
            """Read from multiple input directories and write to multiple output files and directories.

            Args:
                input_dirs: The input directory paths
                output_files: The output file paths
                output_dirs: The output directory paths
            """
            print(f"Received input dirs: {input_dirs}.")
            print(f"Received output files: {output_files}.")
            print(f"Received output dirs: {output_dirs}.")
            for output_dir in output_dirs:
                output_dir.mkdir()
            for output_file in output_files:
                output_file.write_text("hello")

        input_dir_1 = working_tmp_path / "input1"
        input_dir_2 = working_tmp_path / "input2"
        input_dir_1.mkdir()
        input_dir_2.mkdir()
        (input_dir_1 / "a.txt").write_text("hello")
        (input_dir_2 / "b.txt").write_text("world")
        input_fn1 = input_dir_1.name
        input_fn2 = input_dir_2.name
        output_file_1 = working_tmp_path / "output1.txt"
        output_file_2 = working_tmp_path / "output2.txt"
        output_fn1 = output_file_1.name
        output_fn2 = output_file_2.name
        output_dir_1 = working_tmp_path / "output1"
        output_dir_2 = working_tmp_path / "output2"
        output_fn3 = output_dir_1.name
        output_fn4 = output_dir_2.name

        tokens = [
            "--input-dirs",
            input_fn1,
            "--input-dirs",
            input_fn2,
            "--output-files",
            output_fn1,
            "--output-files",
            output_fn2,
            "--output-dirs",
            output_fn3,
            "--output-dirs",
            output_fn4,
        ]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        _, action = assert_crate(
            working_tmp_path,
            action_id=f"myapp --input-dirs {input_fn1} --input-dirs {input_fn2} --output-files {output_fn1} --output-files {output_fn2} --output-dirs {output_fn3} --output-dirs {output_fn4}",
            input_ids={input_fn1 + "/", input_fn2 + "/"},
            output_ids={
                output_fn1,
                output_fn2,
                output_fn3 + "/",
                output_fn4 + "/",
            },
        )


class TestAsync:
    def app_with_async(self) -> App:
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        async def main():
            await asyncio.sleep(0)
            print("Hello from async main!")

        return app

    def test_callable(self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        app = self.app_with_async()
        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Hello from async main!" in captured.out
        assert_crate(
            working_tmp_path,
            action_id="main",
            input_ids=set(),
            output_ids=set(),
            instrument_id="main@1.0.0",
        )

    @pytest.mark.asyncio
    async def test_run_async(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = self.app_with_async()
        tokens = ""

        with record_cyclopts(app, tokens=tokens):
            await app.run_async(tokens=tokens)

        captured = capsys.readouterr()
        assert "Hello from async main!" in captured.out
        assert_crate(
            working_tmp_path,
            action_id="main",
            input_ids=set(),
            output_ids=set(),
            instrument_id="main@1.0.0",
        )


class TestStdioPath:
    def test_stdin_on_input_file(
        self,
        working_tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "sys.stdin", TextIOWrapper(BytesIO(b"hello\n"), encoding="utf-8")
        )

        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def main(input: Annotated[StdioPath, INPUT_FILE], /):
            body = input.read_text()
            print(f"Received input from {input}.")
            print(f"Input content: {body}")

        tokens = ["-"]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert "Received input from -" in captured.out
        assert "Input content: hello" in captured.out
        assert_crate(
            working_tmp_path,
            action_id="main -",
            input_ids=set(),  # stdin is not recorded as an input file
            output_ids=set(),
            instrument_id="main@1.0.0",
        )

    def test_stdout_on_output_file(
        self, working_tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        app = App(result_action="return_value", version="1.0.0")

        @app.default
        def main(output: Annotated[StdioPath, OUTPUT_FILE], /):
            output.write_text("hello")

        tokens = ["-"]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        captured = capsys.readouterr()
        assert captured.err == ""  # nothing should be written to stderr
        assert "hello" in captured.out

        assert_crate(
            working_tmp_path,
            action_id="main -",
            input_ids=set(),
            output_ids=set(),  # stdout is not recorded as an output file
            instrument_id="main@1.0.0",
        )


class TestDataclass:
    def test_nested_model(self, working_tmp_path: Path):

        @dataclass
        class IOConfig:
            """The IO configuration for the app.

            Args:
                output: The output file path
            """

            output: Annotated[Path, OUTPUT_FILE]

        @dataclass
        class Config:
            """The configuration for the app.

            Args:
                io: The IO configuration
            """

            io: IOConfig

        app = App(name="myapp", result_action="return_value")

        @app.default
        def main(config: Config):
            """Main command with nested dataclass config.

            Args:
                config: The configuration for the app, including IO paths.
            """
            config.io.output.write_text("DATA")

        output_file = working_tmp_path / "output.txt"
        tokens = [str(output_file.name)]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        assert output_file.read_text() == "DATA"
        _, action = assert_crate(
            working_tmp_path,
            action_id="myapp output.txt",
            input_ids=set(),
            output_ids={"output.txt"},
        )
        outputs = action["result"]
        assert len(outputs) == 1
        output = outputs[0]
        assert output.id == "output.txt"
        assert output["name"] == "output.txt"
        assert output["description"] == "The output file path"


class TestPydantic:
    def test_nested_model(self, working_tmp_path: Path):

        class IOConfig(BaseModel):
            """The IO configuration for the app.

            Args:
                output: The output file path
            """

            output: Annotated[Path, OUTPUT_FILE]

        class Config(BaseModel):
            """The configuration for the app.

            Args:
                io: The IO configuration
            """

            io: IOConfig

        app = App(name="myapp", result_action="return_value")

        @app.default
        def main(config: Config):
            """Main command with nested Pydantic config.

            Args:
                config: The configuration for the app, including IO paths.
            """
            config.io.output.write_text("DATA")

        output_file = working_tmp_path / "output.txt"
        tokens = [str(output_file.name)]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        assert output_file.read_text() == "DATA"
        _, action = assert_crate(
            working_tmp_path,
            action_id="myapp output.txt",
            input_ids=set(),
            output_ids={"output.txt"},
        )
        outputs = action["result"]
        assert len(outputs) == 1
        output = outputs[0]
        assert output.id == "output.txt"
        assert output["name"] == "output.txt"
        assert output["description"] == "The output file path"


class TestAttrs:
    def test_nested_model(self, working_tmp_path: Path):

        @define
        class IOConfig:
            """The IO configuration for the app.

            Args:
                output: The output file path
            """

            output: Annotated[Path, OUTPUT_FILE]

        @define
        class Config:
            """The configuration for the app.

            Args:
                io: The IO configuration
            """

            io: IOConfig

        app = App(name="myapp", result_action="return_value")

        @app.default
        def main(config: Config):
            """Main command with nested Pydantic config.

            Args:
                config: The configuration for the app, including IO paths.
            """
            config.io.output.write_text("DATA")

        output_file = working_tmp_path / "output.txt"
        tokens = [str(output_file.name)]
        with record_cyclopts(app, tokens=tokens):
            app(tokens=tokens)

        assert output_file.read_text() == "DATA"
        _, action = assert_crate(
            working_tmp_path,
            action_id="myapp output.txt",
            input_ids=set(),
            output_ids={"output.txt"},
        )
        outputs = action["result"]
        assert len(outputs) == 1
        output = outputs[0]
        assert output.id == "output.txt"
        assert output["name"] == "output.txt"
        assert output["description"] == "The output file path"


# TODO test lazy loading, https://cyclopts.readthedocs.io/en/stable/lazy_loading.html#lazy-loading


class Test_value2paths:
    def test_single_path(self, tmp_path: Path):
        path = tmp_path / "test.txt"
        path.write_text("test")

        paths = value2paths(path)

        assert paths == [path]

    def test_list_of_paths(self, tmp_path: Path):
        path1 = tmp_path / "test1.txt"
        path2 = tmp_path / "test2.txt"
        path1.write_text("test1")
        path2.write_text("test2")

        paths = value2paths([path1, path2])

        assert paths == [path1, path2]

    def test_duplicate_paths(self, tmp_path: Path):
        path = tmp_path / "test.txt"
        path.write_text("test")

        paths = value2paths([path, path])

        assert paths == [path]

    def test_stdiopath_dash_ignored(self, caplog: pytest.LogCaptureFixture):
        paths = value2paths(StdioPath("-"))

        assert paths == []
        assert (
            "Unable to convert stdin/stdout file-like object to Path, ignoring it"
            in caplog.text
        )

    def test_mixed_paths_with_stdiopath_dash(self, tmp_path: Path):
        path = tmp_path / "input.txt"

        paths = value2paths([path, StdioPath("-")])

        assert paths == [path]

    def test_tuple_path_int(self, tmp_path: Path):
        path = tmp_path / "input.txt"

        paths = value2paths((path, 42))

        assert paths == [path]
