from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from rocrate.rocrate import Metadata

from rocrate_action_recorder.adapters.click import (
    IOArgumentNames,
    collect_record_info_from_click,
    recorded_click,
)
from rocrate_action_recorder.core import IOArgumentPath, IOArgumentPaths, Program


class Test_collect_record_info_from_click:
    def test_1inputfile_1outputfile_paths(self, tmp_path: Path):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--input",
            "input",
            type=click.Path(path_type=Path),
            required=True,
            help="Input file",
        )
        @click.option(
            "--output",
            "output",
            type=click.Path(path_type=Path),
            required=True,
            help="Output file",
        )
        def cmd(input: Path, output: Path) -> None:
            _ = input
            _ = output

        input_file = tmp_path / "input.txt"
        output_file = tmp_path / "output.txt"
        input_file.write_text("hello")

        with cmd.make_context(
            "myscript",
            ["--input", str(input_file), "--output", str(output_file)],
        ) as ctx:
            names = IOArgumentNames(input_files=["input"], output_files=["output"])

            program, paths = collect_record_info_from_click(ctx, ctx.params, names)

        expected_program = Program(
            name="myscript",
            description="Example Click CLI",
            version=None,
        )
        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="Input file")],
            output_files=[IOArgumentPath(name="output", path=output_file, help="Output file")],
        )
        assert program == expected_program
        assert paths == expected_paths

    def test_multiple_empty(self):
        @click.command(name="processor", help="Process files")
        @click.option(
            "--inputs",
            "inputs",
            multiple=True,
            type=click.Path(path_type=Path),
            help="Input files",
        )
        def cmd(inputs: tuple[Path, ...]) -> None:
            _ = inputs

        with cmd.make_context("processor", []) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["inputs"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[],
        )
        assert paths == expected_paths

    def test_multiple_single(self):
        @click.command(name="processor", help="Process files")
        @click.option(
            "--inputs",
            "inputs",
            multiple=True,
            type=click.Path(path_type=Path),
            help="Input files",
        )
        def cmd(inputs: tuple[Path, ...]) -> None:
            _ = inputs

        input_file = Path("input.txt")
        with cmd.make_context("processor", ["--inputs", str(input_file)]) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["inputs"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="inputs", path=input_file, help="Input files")],
        )
        assert paths == expected_paths

    def test_multiple_multiple(self):
        @click.command(name="processor", help="Process files")
        @click.option(
            "--inputs",
            "inputs",
            multiple=True,
            type=click.Path(path_type=Path),
            help="Input files",
        )
        def cmd(inputs: tuple[Path, ...]) -> None:
            _ = inputs

        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        with cmd.make_context(
            "processor",
            [
                "--inputs",
                str(input_files[0]),
                "--inputs",
                str(input_files[1]),
                "--inputs",
                str(input_files[2]),
            ],
        ) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["inputs"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_files[0], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[1], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[2], help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_multiple_with_duplicates(self):
        @click.command(name="processor", help="Process files")
        @click.option(
            "--inputs",
            "inputs",
            multiple=True,
            type=click.Path(path_type=Path),
            help="Input files",
        )
        def cmd(inputs: tuple[Path, ...]) -> None:
            _ = inputs

        file1 = Path("file1.txt")
        file2 = Path("file2.txt")
        with cmd.make_context(
            "processor",
            ["--inputs", str(file1), "--inputs", str(file1), "--inputs", str(file2)],
        ) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["inputs"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=file1, help="Input files"),
                IOArgumentPath(name="inputs", path=file2, help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_nargs_int(self):
        @click.command(name="processor", help="Process files")
        @click.option(
            "--inputs",
            "inputs",
            nargs=2,
            type=click.Path(path_type=Path),
            required=True,
            help="Input files",
        )
        def cmd(inputs: tuple[Path, Path]) -> None:
            _ = inputs

        input_files = [Path("file1.txt"), Path("file2.txt")]
        with cmd.make_context(
            "processor",
            ["--inputs", str(input_files[0]), str(input_files[1])],
        ) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["inputs"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_files[0], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[1], help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_positional_args(self):
        @click.command(name="myscript", help="Process files")
        @click.argument("input", type=click.Path(path_type=Path))
        @click.argument("output", type=click.Path(path_type=Path))
        def cmd(input: Path, output: Path) -> None:
            _ = input
            _ = output

        input_file = Path("input.txt")
        output_file = Path("output.txt")

        with cmd.make_context("myscript", [str(input_file), str(output_file)]) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["input"], output_files=["output"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="")],
            output_files=[IOArgumentPath(name="output", path=output_file, help="")],
        )
        assert paths == expected_paths

    def test_arg_with_default(self):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--input",
            "input",
            type=click.Path(path_type=Path),
            default=Path("input.txt"),
            help="Input file",
        )
        def cmd(input: Path) -> None:
            _ = input

        with cmd.make_context("myscript", []) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["input"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=Path("input.txt"), help="Input file")],
        )
        assert paths == expected_paths

    def test_args_with_flags(self):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "-i",
            "--input",
            "input",
            type=click.Path(path_type=Path),
            help="Input file",
        )
        def cmd(input: Path) -> None:
            _ = input

        input_file = Path("input.txt")
        with cmd.make_context("myscript", ["-i", str(input_file)]) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["input"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="Input file")],
        )
        assert paths == expected_paths

    def test_subcommand_single_level(self, tmp_path: Path):
        @click.group(name="git", help="Git version control system")
        def cli() -> None:
            return None

        @cli.command(name="commit", help="Record changes to repository")
        @click.option(
            "--input",
            "input",
            type=click.Path(path_type=Path),
            required=True,
            help="File to commit",
        )
        def commit(input: Path) -> None:
            _ = input

        input_file = tmp_path / "changes.txt"
        args = ["commit", "--input", str(input_file)]

        with cli.make_context("git", args) as parent_ctx:
            subcommand_name, subcommand, remaining_args = cli.resolve_command(parent_ctx, args)
            with subcommand.make_context(
                subcommand_name,
                remaining_args,
                parent=parent_ctx,
            ) as command_ctx:
                program, paths = collect_record_info_from_click(
                    command_ctx,
                    command_ctx.params,
                    IOArgumentNames(input_files=["input"]),
                )

        expected_program = Program(
            name="git",
            description="Git version control system",
            version=None,
            subcommands={
                "commit": Program(
                    name="commit",
                    description="Record changes to repository",
                    version=None,
                )
            },
        )
        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="File to commit")],
        )
        assert program == expected_program
        assert paths == expected_paths

    def test_subcommand_nested_levels(self, tmp_path: Path):
        @click.group(name="git", help="Git version control system")
        def cli() -> None:
            return None

        @cli.group(name="remote", help="Manage remote repositories")
        def remote() -> None:
            return None

        @remote.command(name="add", help="Add a new remote")
        @click.option(
            "--input",
            "input",
            type=click.Path(path_type=Path),
            required=True,
            help="Config file",
        )
        def add(input: Path) -> None:
            _ = input

        input_file = tmp_path / "git_config.txt"
        args = ["remote", "add", "--input", str(input_file)]

        with cli.make_context("git", args) as root_ctx:
            remote_name, remote_cmd, remaining_args = cli.resolve_command(root_ctx, args)
            with remote_cmd.make_context(
                remote_name,
                remaining_args,
                parent=root_ctx,
            ) as remote_ctx:
                add_name, add_cmd, add_args = remote_cmd.resolve_command(remote_ctx, remaining_args)
                with add_cmd.make_context(
                    add_name,
                    add_args,
                    parent=remote_ctx,
                ) as add_ctx:
                    program, paths = collect_record_info_from_click(
                        add_ctx,
                        add_ctx.params,
                        IOArgumentNames(input_files=["input"]),
                    )

        expected_program = Program(
            name="git",
            description="Git version control system",
            version=None,
            subcommands={
                "remote": Program(
                    name="remote",
                    description="Manage remote repositories",
                    version=None,
                    subcommands={
                        "add": Program(
                            name="add",
                            description="Add a new remote",
                            version=None,
                        )
                    },
                )
            },
        )
        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="Config file")],
        )
        assert program == expected_program
        assert paths == expected_paths

    def test_subcommand_with_parent_flags(self):
        @click.group(name="git", help="Git version control system")
        @click.option("--no-pager", is_flag=True, help="Do not pipe output into a pager")
        def cli(no_pager: bool) -> None:
            _ = no_pager

        @cli.command(name="status", help="Show working tree status")
        def status() -> None:
            return None

        args = ["--no-pager", "status"]
        with cli.make_context("git", args) as parent_ctx:
            subcommand_name, subcommand, remaining_args = cli.resolve_command(parent_ctx, args)
            with subcommand.make_context(
                subcommand_name,
                remaining_args,
                parent=parent_ctx,
            ) as command_ctx:
                program, paths = collect_record_info_from_click(
                    command_ctx,
                    command_ctx.params,
                    IOArgumentNames(),
                )

        expected_program = Program(
            name="git",
            description="Git version control system",
            version=None,
            subcommands={
                "status": Program(
                    name="status",
                    description="Show working tree status",
                    version=None,
                )
            },
        )
        expected_paths = IOArgumentPaths()
        assert program == expected_program
        assert paths == expected_paths

    def test_1inputdir_1outputdir_paths(self, tmp_path: Path):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--input-dir",
            "input_dir",
            type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
            required=True,
            help="Input directory",
        )
        @click.option(
            "--output-dir",
            "output_dir",
            type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
            required=True,
            help="Output directory",
        )
        def cmd(input_dir: Path, output_dir: Path) -> None:
            _ = input_dir
            _ = output_dir

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        with cmd.make_context(
            "myscript",
            ["--input-dir", str(input_dir), "--output-dir", str(output_dir)],
        ) as ctx:
            names = IOArgumentNames(input_dirs=["input_dir"], output_dirs=["output_dir"])

            program, paths = collect_record_info_from_click(ctx, ctx.params, names)

        expected_program = Program(
            name="myscript",
            description="Example Click CLI",
            version=None,
        )
        expected_paths = IOArgumentPaths(
            input_dirs=[IOArgumentPath(name="input_dir", path=input_dir, help="Input directory")],
            output_dirs=[
                IOArgumentPath(
                    name="output_dir",
                    path=output_dir,
                    help="Output directory",
                )
            ],
        )
        assert program == expected_program
        assert paths == expected_paths

    def test_filetype_input_output_paths(self, tmp_path: Path):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--input",
            "input",
            type=click.File(mode="r"),
            required=True,
            help="Input file",
        )
        @click.option(
            "--output",
            "output",
            type=click.File(mode="w", encoding="UTF-8"),
            required=True,
            help="Output file",
        )
        def cmd(input: click.utils.LazyFile, output: click.utils.LazyFile) -> None:
            _ = input
            _ = output

        input_file = tmp_path / "input.txt"
        output_file = tmp_path / "output.txt"
        input_file.write_text("hello")

        with cmd.make_context(
            "myscript",
            ["--input", str(input_file), "--output", str(output_file)],
        ) as ctx:
            names = IOArgumentNames(input_files=["input"], output_files=["output"])

            program, paths = collect_record_info_from_click(ctx, ctx.params, names)

        expected_program = Program(
            name="myscript",
            description="Example Click CLI",
            version=None,
        )
        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="Input file")],
            output_files=[IOArgumentPath(name="output", path=output_file, help="Output file")],
        )
        assert program == expected_program
        assert paths == expected_paths

    def test_filetype_stdin_ignored(self, caplog: pytest.LogCaptureFixture):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--input",
            "input",
            type=click.File(mode="r"),
            required=True,
            help="Input file",
        )
        def cmd(input: click.utils.LazyFile) -> None:
            _ = input

        with cmd.make_context(
            "myscript",
            ["--input", "-"],
        ) as ctx:
            names = IOArgumentNames(input_files=["input"])

            _, paths = collect_record_info_from_click(ctx, ctx.params, names)

        expected_paths = IOArgumentPaths(
            input_files=[],
        )
        assert paths == expected_paths
        assert "Unable to convert stdin/stdout file-like object to Path, ignoring it" in caplog.text
        assert "has no associated path-like argument value" in caplog.text

    def test_filetype_multiple_with_stdin(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--input",
            "input",
            type=click.File(mode="r"),
            multiple=True,
            required=True,
            help="Input file",
        )
        def cmd(input: tuple[click.utils.LazyFile, ...]) -> None:
            _ = input

        input_file = tmp_path / "somefile"
        input_file.write_text("hello")

        with cmd.make_context(
            "myscript",
            ["--input", str(input_file), "--input", "-"],
        ) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["input"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="Input file")],
        )
        assert paths == expected_paths
        assert "Unable to convert stdin/stdout file-like object to Path, ignoring it" in caplog.text
        assert "has no associated path-like argument value" not in caplog.text

    def test_str_arg(self, tmp_path: Path):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option("--input", "input", type=str, help="Input file")
        def cmd(input: str) -> None:
            _ = input

        input_file = tmp_path / "input.txt"
        with cmd.make_context("myscript", ["--input", str(input_file)]) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["input"]),
            )

        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=input_file, help="Input file")],
            output_files=[],
        )
        assert paths == expected_paths

    def test_integer_arg(self):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option("--count", "count", type=int, help="A count value")
        def cmd(count: int) -> None:
            _ = count

        with cmd.make_context("myscript", ["--count", "5"]) as ctx:
            _, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(input_files=["count"]),
            )
            assert paths == IOArgumentPaths(input_files=[])

    def test_overwrite_software_version(self):
        @click.command(name="myscript", help="Example Click CLI")
        def cmd() -> None:
            return None

        with cmd.make_context("myscript", []) as ctx:
            program, _ = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(),
                software_version="2.0.0",
            )

        assert program.version == "2.0.0"

    def test_absent_optional_path(self):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--output",
            "output",
            type=click.Path(path_type=Path),
            required=False,
            help="Output file",
        )
        def cmd(output: Path | None) -> None:
            _ = output

        with cmd.make_context("myscript", []) as ctx:
            program, paths = collect_record_info_from_click(
                ctx,
                ctx.params,
                IOArgumentNames(output_files=["output"]),
            )

        expected_program = Program(
            name="myscript",
            description="Example Click CLI",
            version=None,
        )
        expected_paths = IOArgumentPaths()
        assert program == expected_program
        assert paths == expected_paths

    def test_filetype_stdout_dash_raises_typeerror(self):
        @click.command(name="myscript", help="Example Click CLI")
        @click.option(
            "--output",
            "output",
            type=click.File(mode="w"),
            required=True,
            help="Output file",
        )
        def cmd(output: click.utils.LazyFile) -> None:
            _ = output

        with cmd.make_context("myscript", ["--output", "-"]) as ctx:
            names = IOArgumentNames(output_files=["output"])

            with pytest.raises(
                TypeError,
                match="argument should be a str or an os.PathLike object",
            ):
                collect_record_info_from_click(ctx, ctx.params, names)


class Test_recorded_click:
    def test_defaults(self):
        runner = CliRunner()

        @click.command(name="myscript")
        @click.argument("input", type=click.Path(path_type=Path, exists=True))
        @click.argument("output", type=click.Path(path_type=Path))
        @recorded_click(
            input_files=["input"],
            output_files=["output"],
            dataset_license="CC-BY-4.0",
        )
        def handler(input: Path, output: Path) -> int:
            return output.write_text(input.read_text().upper())

        with runner.isolated_filesystem():
            Path("input.txt").write_text("hello")

            result = runner.invoke(handler, ["input.txt", "output.txt"])

            crate_meta = Path(Metadata.BASENAME)
            assert result.exit_code == 0
            assert crate_meta.exists()

    def test_without_enabled_arg(self):
        runner = CliRunner()

        @click.command(name="myscript")
        @click.option("--record/--no-record", default=True, help="Enable recording")
        @click.argument("input", type=click.Path(path_type=Path, exists=True))
        @click.argument("output", type=click.Path(path_type=Path))
        @recorded_click(
            input_files=["input"],
            output_files=["output"],
            dataset_license="CC-BY-4.0",
            enabled_argument="record",
        )
        def handler(record: bool, input: Path, output: Path) -> int:
            _ = record
            return output.write_text(input.read_text().upper())

        with runner.isolated_filesystem():
            Path("input.txt").write_text("hello")

            result = runner.invoke(handler, ["--no-record", "input.txt", "output.txt"])

            crate_meta = Path(Metadata.BASENAME)
            assert result.exit_code == 0
            assert not crate_meta.exists()

    def test_with_truthy_enabled_arg(self):
        runner = CliRunner()

        @click.command(name="myscript")
        @click.option("--record/--no-record", default=True, help="Enable recording")
        @click.argument("input", type=click.Path(path_type=Path, exists=True))
        @click.argument("output", type=click.Path(path_type=Path))
        @recorded_click(
            input_files=["input"],
            output_files=["output"],
            dataset_license="CC-BY-4.0",
            enabled_argument="record",
        )
        def handler(record: bool, input: Path, output: Path) -> int:
            _ = record
            return output.write_text(input.read_text().upper())

        with runner.isolated_filesystem():
            Path("input.txt").write_text("hello")

            result = runner.invoke(handler, ["input.txt", "output.txt"])

            crate_meta = Path(Metadata.BASENAME)
            assert result.exit_code == 0
            assert crate_meta.exists()

    def test_with_all_ios(self):
        runner = CliRunner()

        @click.command(name="myscript")
        @click.argument("input", type=click.Path(path_type=Path, exists=True))
        @click.argument("output", type=click.Path(path_type=Path))
        @click.argument("input_dir", type=click.Path(path_type=Path, exists=True))
        @click.argument("output_dir", type=click.Path(path_type=Path))
        @recorded_click(
            input_files=["input"],
            output_files=["output"],
            input_dirs=["input_dir"],
            output_dirs=["output_dir"],
            dataset_license="CC-BY-4.0",
        )
        def handler(input: Path, output: Path, input_dir: Path, output_dir: Path) -> None:
            _ = input_dir
            output.write_text(input.read_text().upper())
            output_dir.mkdir()

        with runner.isolated_filesystem():
            Path("input.txt").write_text("test data\n")
            Path("input_dir").mkdir()

            result = runner.invoke(
                handler,
                ["input.txt", "output.txt", "input_dir", "output_dir"],
            )

            crate_meta = Path(Metadata.BASENAME)
            assert result.exit_code == 0
            assert crate_meta.exists()
            body = crate_meta.read_text()
            assert "input.txt" in body
            assert "output.txt" in body
            assert "input_dir" in body
            assert "output_dir" in body
            assert "CC-BY-4.0" in body
