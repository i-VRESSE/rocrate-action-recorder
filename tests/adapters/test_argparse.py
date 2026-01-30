from argparse import ArgumentParser, FileType, Namespace
from pathlib import Path

import pytest

from rocrate_action_recorder.adapters.argparse import (
    version_from_parser,
    collect_record_info_from_argparse,
    IOArgumentNames,
    MissingDestArgparseSubparserError,
)
from rocrate_action_recorder.core import (
    IOArgumentPaths,
    IOArgumentPath,
    Program,
)


class Test_version_from_parser:
    def test_golden_path(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--version", action="version", version="%(prog)s 2.0.1")

        version = version_from_parser(parser)

        assert version == "2.0.1"

    def test_bare_version(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--version", action="version", version="1.2.3")

        version = version_from_parser(parser)

        assert version == "1.2.3"

    def test_no_version(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--input", type=Path, help="Input file")
        # No version argument added

        version = version_from_parser(parser)

        assert version is None


class Test_collect_record_info_from_argparse:
    def test_1inputfile_1outputfile_paths_versioned(self, tmp_path: Path):
        parser = ArgumentParser(prog="myscript", description="Example CLI")
        parser.add_argument("--version", action="version", version="%(prog)s 1.2.3")
        parser.add_argument("input", type=Path, help="Input file")
        parser.add_argument("output", type=Path, help="Output file")
        input_file = tmp_path / "input.txt"
        output_file = tmp_path / "output.txt"
        ns = parser.parse_args([str(input_file), str(output_file)])
        names = IOArgumentNames(
            input_files=["input"],
            output_files=["output"],
        )

        program, paths = collect_record_info_from_argparse(parser, ns, names)

        expected_program = Program(
            name="myscript",
            description="Example CLI",
            version="1.2.3",
        )
        assert program == expected_program
        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_file, help="Input file")
            ],
            output_files=[
                IOArgumentPath(name="output", path=output_file, help="Output file")
            ],
        )
        assert paths == expected_paths

    def test_nargs_star_empty(self):
        """Test argparse_info with nargs='*' and no values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        ns = parser.parse_args([])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[],
        )
        assert paths == expected_paths

    def test_nargs_star_single(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        input_file = Path("input.txt")
        ns = parser.parse_args(["--inputs", str(input_file)])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_file, help="Input files")
            ],
        )
        assert paths == expected_paths

    def test_nargs_star_multiple(self):
        """Test argparse_info with nargs='*' and multiple values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_files[0], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[1], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[2], help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_nargs_star_with_duplicates(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="*", type=Path, help="Input files")
        file1 = Path("file1.txt")
        file2 = Path("file2.txt")
        input_files = [file1, file1, file2]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )
        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=file1, help="Input files"),
                IOArgumentPath(name="inputs", path=file2, help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_nargs_plus_single(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="+", type=Path, help="Input files")
        input_file = Path("input.txt")
        ns = parser.parse_args(["--inputs", str(input_file)])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_file, help="Input files")
            ],
        )
        assert paths == expected_paths

    def test_nargs_plus_multiple(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs="+", type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_files[0], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[1], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[2], help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_nargs_int(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", nargs=2, type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt")]
        ns = parser.parse_args(["--inputs"] + [str(f) for f in input_files])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_files[0], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[1], help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_nargs_question_with_value(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--input", nargs="?", type=Path, help="Input file")
        input_file = Path("input.txt")
        ns = parser.parse_args(["--input", str(input_file)])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_file, help="Input file")
            ],
        )
        assert paths == expected_paths

    def test_nargs_question_without_value(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--input", nargs="?", type=Path, help="Input file")
        ns = parser.parse_args([])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[],
        )
        assert paths == expected_paths

    def test_action_append_multiple(self):
        """Test argparse_info with action='append' and multiple values provided."""
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument("--inputs", action="append", type=Path, help="Input files")
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(
            [
                "--inputs",
                str(input_files[0]),
                "--inputs",
                str(input_files[1]),
                "--inputs",
                str(input_files[2]),
            ]
        )

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_files[0], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[1], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[2], help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_action_extend_multiple(self):
        parser = ArgumentParser(prog="processor", description="Process files")
        parser.add_argument(
            "--inputs", action="extend", nargs="+", type=Path, help="Input files"
        )
        input_files = [Path("file1.txt"), Path("file2.txt"), Path("file3.txt")]
        ns = parser.parse_args(
            [
                "--inputs",
                str(input_files[0]),
                str(input_files[1]),
                "--inputs",
                str(input_files[2]),
            ]
        )
        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["inputs"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="inputs", path=input_files[0], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[1], help="Input files"),
                IOArgumentPath(name="inputs", path=input_files[2], help="Input files"),
            ],
        )
        assert paths == expected_paths

    def test_positional_args(self):
        parser = ArgumentParser(prog="myscript", description="Process files")
        parser.add_argument("input", type=Path, help="Input file")
        parser.add_argument("output", type=Path, help="Output file")

        input_file = Path("input.txt")
        output_file = Path("output.txt")
        ns = parser.parse_args([str(input_file), str(output_file)])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
                output_files=["output"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_file, help="Input file")
            ],
            output_files=[
                IOArgumentPath(name="output", path=output_file, help="Output file")
            ],
        )
        assert paths == expected_paths

    def test_arg_with_default(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument(
            "--input", type=Path, default=Path("input.txt"), help="Input file"
        )
        # Don't provide input, it will use default
        ns = parser.parse_args([])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=Path("input.txt"), help="Input file")
            ],
        )
        assert paths == expected_paths

    def test_args_with_dest(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("--input", dest="myinput", type=Path, help="Input file")
        parser.add_argument("--output", dest="myoutput", type=Path, help="Output file")

        input_file = Path("input.txt")
        output_file = Path("output.txt")
        ns = parser.parse_args(
            ["--input", str(input_file), "--output", str(output_file)]
        )

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["myinput"],
                output_files=["myoutput"],
            ),
        )
        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="myinput", path=input_file, help="Input file")
            ],
            output_files=[
                IOArgumentPath(name="myoutput", path=output_file, help="Output file")
            ],
        )
        assert paths == expected_paths

    def test_args_with_flags(self):
        parser = ArgumentParser(
            prog="myscript", description="Process input and generate output"
        )
        parser.add_argument("-i", "--input", type=Path, help="Input file")

        input_file = Path("input.txt")
        ns = parser.parse_args(["-i", str(input_file)])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_file, help="Input file")
            ],
        )
        assert paths == expected_paths

    def test_subcommand_single_level(self, tmp_path: Path):
        parser = ArgumentParser(prog="git", description="Git version control system")
        subparsers = parser.add_subparsers(dest="command")
        commit_parser = subparsers.add_parser(
            "commit",
            description="Record changes to repository",
        )
        commit_parser.add_argument("--input", type=Path, help="File to commit")

        input_path = tmp_path / "changes.txt"
        args = ["commit", "--input", str(input_path)]
        ns = parser.parse_args(args)

        program, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_program = Program(
            name="git",
            description="Git version control system",
            version=None,
            subcommands={
                "commit": Program(
                    name="git commit",
                    description="Record changes to repository",
                    version=None,
                )
            },
        )
        assert program == expected_program
        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_path, help="File to commit")
            ],
        )
        assert paths == expected_paths

    def test_subcommand_nested_levels(self, tmp_path: Path):
        """Test argparse_info extracts nested subcommands (e.g., git remote add)."""
        parser = ArgumentParser(prog="git", description="Git version control system")
        subparsers = parser.add_subparsers(dest="command", help="Git commands")
        remote_parser = subparsers.add_parser(
            "remote", description="Manage remote repositories"
        )
        remote_subparsers = remote_parser.add_subparsers(dest="action")
        add_parser = remote_subparsers.add_parser("add", description="Add a new remote")
        add_parser.add_argument("--input", type=Path, help="Config file")

        input_path = tmp_path / "git_config.txt"
        args = [
            "remote",
            "add",
            "--input",
            str(input_path),
        ]
        ns = parser.parse_args(args)

        program, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_program = Program(
            name="git",
            description="Git version control system",
            version=None,
            subcommands={
                "remote": Program(
                    name="git remote",
                    description="Manage remote repositories",
                    version=None,
                    subcommands={
                        "add": Program(
                            name="git remote add",
                            description="Add a new remote",
                            version=None,
                        )
                    },
                )
            },
        )
        assert program == expected_program
        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_path, help="Config file")
            ],
        )
        assert paths == expected_paths

    def test_subcommand_missing_dest(self, tmp_path: Path):
        """Test that missing dest parameter in add_subparsers raises ValueError."""
        parser = ArgumentParser(prog="tool")
        subparsers = parser.add_subparsers()  # Missing dest parameter
        action_parser = subparsers.add_parser("action")
        action_parser.add_argument("--input", type=Path, help="Input file")

        input_path = tmp_path / "input.txt"
        args = ["action", "--input", str(input_path)]
        ns = parser.parse_args(args)

        with pytest.raises(
            MissingDestArgparseSubparserError,
        ):
            collect_record_info_from_argparse(
                parser,
                ns,
                IOArgumentNames(
                    input_files=["input"],
                ),
            )

    def test_subcommand_with_parent_flags(self, tmp_path: Path):
        """Test argparse_info handles flags before subcommand (e.g., git --no-pager status)."""
        parser = ArgumentParser(prog="git", description="Git version control system")
        parser.add_argument(
            "--no-pager", action="store_true", help="Do not pipe output into a pager"
        )
        subparsers = parser.add_subparsers(dest="command")
        subparsers.add_parser("status", description="Show working tree status")

        args = [
            "--no-pager",
            "status",
        ]
        ns = parser.parse_args(args)

        program, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(),
        )
        expected_program = Program(
            name="git",
            description="Git version control system",
            version=None,
            subcommands={
                "status": Program(
                    name="git status",
                    description="Show working tree status",
                    version=None,
                )
            },
        )
        assert program == expected_program
        expected_paths = IOArgumentPaths()
        assert paths == expected_paths

    def test_subcommand_with_parent_file(self, tmp_path: Path):
        """git --config somefile status"""
        parser = ArgumentParser(prog="git", description="Git version control system")
        parser.add_argument("--config", type=Path, help="Path to git config file")
        subparsers = parser.add_subparsers(dest="command")
        subparsers.add_parser("status", description="Show working tree status")

        config_path = tmp_path / "somefile"
        args = [
            "--config",
            str(config_path),
            "status",
        ]
        ns = parser.parse_args(args)

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["config"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(
                    name="config", path=config_path, help="Path to git config file"
                )
            ],
        )
        assert paths == expected_paths

    def test_filetype_stdin(self, caplog: pytest.LogCaptureFixture):
        parser = ArgumentParser(prog="myscript")
        parser.add_argument(
            "input",
            type=FileType("r"),
            help="Input file (use '-' for stdin)",
        )

        class FakeStdin:
            def __init__(self):
                self.name = "<stdin>"

        ns = Namespace(input=FakeStdin())

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[],
        )
        assert paths == expected_paths
        assert (
            "Unable to convert stdin/stdout file-like object to Path, ignoring it"
            in caplog.text
        )
        assert "has no associated path-like argument value" in caplog.text

    def test_filetype_stdout(self, caplog: pytest.LogCaptureFixture):
        parser = ArgumentParser(prog="myscript")
        parser.add_argument(
            "output",
            type=FileType("w"),
            help="Output file (use '-' for stdout)",
        )

        class FakeStdout:
            def __init__(self):
                self.name = "<stdout>"

        ns = Namespace(output=FakeStdout())

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                output_files=["output"],
            ),
        )

        expected_paths = IOArgumentPaths(
            output_files=[],
        )
        assert paths == expected_paths
        assert (
            "Unable to convert stdin/stdout file-like object to Path, ignoring it"
            in caplog.text
        )
        assert "has no associated path-like argument value" in caplog.text

    def test_filetype_args(self, tmp_path: Path):
        parser = ArgumentParser(prog="myscript")
        parser.add_argument("--input", type=FileType("r"), help="Input file")
        parser.add_argument(
            "--output", type=FileType("w", encoding="UTF-8"), help="Output file"
        )

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
        with ns.input as inp, ns.output as out:
            out.write(inp.read().upper())

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
                output_files=["output"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_path, help="Input file")
            ],
            output_files=[
                IOArgumentPath(name="output", path=output_path, help="Output file")
            ],
        )
        assert paths == expected_paths

    def test_action_append_filetype_arg_stdin(self, caplog: pytest.LogCaptureFixture):
        # myscript --input somefile --input -
        parser = ArgumentParser(prog="myscript")
        parser.add_argument(
            "--input", type=FileType("r"), action="append", help="Input file"
        )

        class FakeStdin:
            def __init__(self):
                self.name = "<stdin>"

        infile = Path("somefile")
        ns = Namespace(input=[infile, FakeStdin()])

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[IOArgumentPath(name="input", path=infile, help="Input file")],
        )
        assert paths == expected_paths
        assert (
            "Unable to convert stdin/stdout file-like object to Path, ignoring it"
            in caplog.text
        )
        assert "has no associated path-like argument value" not in caplog.text

    def test_str_arg(self, tmp_path: Path):
        parser = ArgumentParser(prog="myscript")
        parser.add_argument("--input", type=str, help="Input file")

        crate_dir = tmp_path
        input_path = crate_dir / "input.txt"

        args = [
            "--input",
            str(input_path),
        ]
        ns = parser.parse_args(args)

        _, paths = collect_record_info_from_argparse(
            parser,
            ns,
            IOArgumentNames(
                input_files=["input"],
            ),
        )

        expected_paths = IOArgumentPaths(
            input_files=[
                IOArgumentPath(name="input", path=input_path, help="Input file")
            ],
            output_files=[],
        )
        assert paths == expected_paths

    def test_integer_arg(self, caplog: pytest.LogCaptureFixture):
        parser = ArgumentParser(prog="myscript")
        parser.add_argument("--count", type=int, help="A count value")

        ns = parser.parse_args(["--count", "5"])

        with pytest.raises(
            TypeError,
            match="argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'int'",
        ):
            collect_record_info_from_argparse(
                parser,
                ns,
                IOArgumentNames(
                    input_files=["count"],
                ),
            )

    def test_overwrite_software_version(self):
        parser = ArgumentParser(prog="myscript", description="Example CLI")
        parser.add_argument("--version", action="version", version="%(prog)s 1.2.3")
        ns = parser.parse_args([])
        names = IOArgumentNames()

        program, _ = collect_record_info_from_argparse(
            parser, ns, names, software_version="2.0.0"
        )

        assert program.version == "2.0.0"
