import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from tests._cli_helpers import RunResult

from dayamlchecker.cli import main
from dayamlchecker.__main__ import main as package_main
from dayamlchecker.yaml_structure import main as checker_main


def _run_dayaml(*args: str) -> RunResult:
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        returncode = main(list(args))
    return RunResult(returncode, stdout_buf.getvalue(), stderr_buf.getvalue())


def test_dayaml_check_dispatches_to_checker_cli():
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")

        result = _run_dayaml("check", str(good))

        assert result.returncode == 0
        assert "1 ok" in result.stdout


def test_dayaml_check_defaults_to_current_directory():
    with TemporaryDirectory() as tmp:
        docassemble_dir = Path(tmp) / "docassemble"
        docassemble_dir.mkdir()
        good = docassemble_dir / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        previous_cwd = Path.cwd()

        try:
            os.chdir(tmp)
            result = _run_dayaml("check")
        finally:
            os.chdir(previous_cwd)

        assert result.returncode == 0
        assert "good.yml" in result.stdout
        assert "1 ok" in result.stdout


def test_dayaml_format_dispatches_to_formatter_cli():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "interview.yml"
        interview.write_text("---\ncode: |\n  x=1\n", encoding="utf-8")

        result = _run_dayaml("format", str(interview))

        assert result.returncode == 0
        assert "reformatted" in result.stdout
        assert interview.read_text(encoding="utf-8") == "---\ncode: |\n  x = 1\n"


def test_dayaml_format_defaults_to_current_directory():
    with TemporaryDirectory() as tmp:
        docassemble_dir = Path(tmp) / "docassemble"
        docassemble_dir.mkdir()
        interview = docassemble_dir / "interview.yml"
        interview.write_text("---\ncode: |\n  x=1\n", encoding="utf-8")
        previous_cwd = Path.cwd()

        try:
            os.chdir(tmp)
            result = _run_dayaml("format")
        finally:
            os.chdir(previous_cwd)

        assert result.returncode == 0
        assert "interview.yml" in result.stdout
        assert "reformatted" in result.stdout
        assert interview.read_text(encoding="utf-8") == "---\ncode: |\n  x = 1\n"


def test_dayaml_help_lists_commands():
    result = _run_dayaml("--help")

    assert result.returncode == 0
    assert "check" in result.stdout
    assert "format" in result.stdout
    assert "defaults to ./docassemble" in result.stdout


def test_dayaml_requires_known_command():
    result = _run_dayaml("unknown")

    assert result.returncode == 2
    assert "unknown command" in result.stderr.lower()


def test_dayaml_no_subcommand_shows_help_on_stderr():
    result = _run_dayaml()

    assert result.returncode == 2
    assert "check" in result.stderr
    assert "format" in result.stderr


def test_dayaml_check_propagates_nonzero_for_invalid_file():
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")

        result = _run_dayaml("check", str(bad))

        assert result.returncode != 0


def test_dayaml_check_returns_zero_for_warning_only_file():
    with TemporaryDirectory() as tmp:
        warning_file = Path(tmp) / "warning.yml"
        warning_file.write_text(
            "---\n"
            "question: Hello\n"
            "fields:\n"
            "  - Preferred salutation: preferred_salutation\n"
            "  - Follow up: follow_up\n"
            "    show if:\n"
            '      code: preferred_salutation == "Ms."\n',
            encoding="utf-8",
        )

        result = _run_dayaml("check", str(warning_file))

        assert result.returncode == 0
        assert "warnings (1)" in result.stdout
        assert "[W410]" in result.stdout


def test_dayaml_format_check_flag_does_not_write():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "interview.yml"
        original = "---\ncode: |\n  x=1\n"
        interview.write_text(original, encoding="utf-8")

        result = _run_dayaml("format", "--check", str(interview))

        assert result.returncode != 0
        assert "Would reformat" in result.stdout
        assert interview.read_text(encoding="utf-8") == original


def test_package_main_aliases_yaml_structure_main():
    """The package entrypoint should directly expose the checker CLI main."""
    assert package_main is checker_main
