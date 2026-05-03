import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import dayamlchecker.yaml_structure as yaml_structure
from dayamlchecker.check_questions_urls import URLCheckResult, URLIssue
from dayamlchecker._files import _collect_yaml_files
from dayamlchecker.__main__ import main as package_main
from dayamlchecker.yaml_structure import (
    YAMLError,
    main,
    parse_ignore_codes,
    process_file,
)


def _write_valid_question(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "question: |\n  What is your name?\nfield: user_name\n",
        encoding="utf-8",
    )


def _write_valid_code_interview(path: Path, *, code: str = "x=1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"mandatory: True\ncode: |\n  {code}\n",
        encoding="utf-8",
    )


def test_collect_yaml_files_recurses_directories_and_dedupes():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        nested = root / "nested"
        nested.mkdir()

        first = root / "a.yml"
        second = nested / "b.yaml"
        other = nested / "ignore.txt"

        first.write_text("question: one\n", encoding="utf-8")
        second.write_text("question: two\n", encoding="utf-8")
        other.write_text("not yaml\n", encoding="utf-8")

        collected = _collect_yaml_files([root, second])

        assert collected == [first, second]


def test_collect_yaml_files_default_ignores_common_directories():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        visible = root / "visible.yml"
        git_file = root / ".git" / "hidden.yml"
        github_file = root / ".github-actions" / "ci.yml"
        build_file = root / "build" / "generated.yml"
        dist_file = root / "dist" / "generated.yml"
        node_modules_file = root / "node_modules" / "package.yml"
        sources_file = root / "sources" / "skip.yml"

        git_file.parent.mkdir(parents=True)
        github_file.parent.mkdir(parents=True)
        build_file.parent.mkdir(parents=True)
        dist_file.parent.mkdir(parents=True)
        node_modules_file.parent.mkdir(parents=True)
        sources_file.parent.mkdir(parents=True)

        visible.write_text("question: visible\n", encoding="utf-8")
        git_file.write_text("question: git\n", encoding="utf-8")
        github_file.write_text("question: github\n", encoding="utf-8")
        build_file.write_text("question: build\n", encoding="utf-8")
        dist_file.write_text("question: dist\n", encoding="utf-8")
        node_modules_file.write_text("question: node_modules\n", encoding="utf-8")
        sources_file.write_text("question: sources\n", encoding="utf-8")

        collected = _collect_yaml_files([root])

        assert collected == [visible]


def test_collect_yaml_files_can_disable_default_ignores():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        visible = root / "visible.yml"
        git_file = root / ".git" / "hidden.yml"
        github_file = root / ".github-actions" / "ci.yml"
        build_file = root / "build" / "generated.yml"
        dist_file = root / "dist" / "generated.yml"
        node_modules_file = root / "node_modules" / "package.yml"
        sources_file = root / "sources" / "skip.yml"

        git_file.parent.mkdir(parents=True)
        github_file.parent.mkdir(parents=True)
        build_file.parent.mkdir(parents=True)
        dist_file.parent.mkdir(parents=True)
        node_modules_file.parent.mkdir(parents=True)
        sources_file.parent.mkdir(parents=True)

        visible.write_text("question: visible\n", encoding="utf-8")
        git_file.write_text("question: git\n", encoding="utf-8")
        github_file.write_text("question: github\n", encoding="utf-8")
        build_file.write_text("question: build\n", encoding="utf-8")
        dist_file.write_text("question: dist\n", encoding="utf-8")
        node_modules_file.write_text("question: node_modules\n", encoding="utf-8")
        sources_file.write_text("question: sources\n", encoding="utf-8")

        collected = _collect_yaml_files([root], include_default_ignores=False)

        assert collected == sorted(
            [
                visible,
                git_file,
                github_file,
                build_file,
                dist_file,
                node_modules_file,
                sources_file,
            ]
        )


def test_collect_yaml_files_uses_docassemble_when_root_has_pyproject():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        root_level_yaml = root / "visible.yml"
        docassemble_yaml = (
            root / "docassemble" / "pkg" / "data" / "questions" / "test.yml"
        )
        docassemble_yaml.parent.mkdir(parents=True)

        root_level_yaml.write_text("question: visible\n", encoding="utf-8")
        docassemble_yaml.write_text("question: test\n", encoding="utf-8")

        collected = _collect_yaml_files([root])

        assert [path.resolve() for path in collected] == [docassemble_yaml.resolve()]


def test_collect_yaml_files_reads_yaml_path_from_pyproject():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
            "[tool.dayaml]\n"
            'yaml_path = "interviews"\n',
            encoding="utf-8",
        )
        configured_yaml = root / "interviews" / "test.yml"
        default_yaml = root / "docassemble" / "ignored.yml"
        configured_yaml.parent.mkdir(parents=True)
        default_yaml.parent.mkdir(parents=True)

        configured_yaml.write_text("question: configured\n", encoding="utf-8")
        default_yaml.write_text("question: default\n", encoding="utf-8")

        collected = _collect_yaml_files([root])

        assert [path.resolve() for path in collected] == [configured_yaml.resolve()]


# ---------------------------------------------------------------------------
# CLI (main()) / process_file() integration tests
# ---------------------------------------------------------------------------


def test_cli_valid_file_exits_zero():
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        assert process_file(str(good)) == "ok"


def test_cli_no_files_found_exits_nonzero():
    with TemporaryDirectory() as tmp:
        # Write a text file, not YAML — _collect_yaml_files skips it, main() returns 1
        txt = Path(tmp) / "readme.txt"
        txt.write_text("hello\n", encoding="utf-8")
        with patch("sys.argv", ["dayamlchecker", str(txt)]):
            assert main() == 1


def test_cli_main_defaults_to_current_directory_when_no_files_passed(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        docassemble_dir = root / "docassemble"
        docassemble_dir.mkdir()
        good = docassemble_dir / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")

        previous_cwd = Path.cwd()
        monkeypatch.chdir(root)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = main([])
        finally:
            monkeypatch.chdir(previous_cwd)

        assert result == 0
        output = buf.getvalue()
        assert output.startswith(".\n")
        assert "1 ok" in output


def test_cli_main_no_files_reads_pyproject_args_from_cwd(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
            "[tool.dayaml]\n"
            'args = ["--no-url-check"]\n',
            encoding="utf-8",
        )
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)

        called = False

        def fake_run_url_check(**kwargs):
            nonlocal called
            called = True
            return URLCheckResult(checked_url_count=0, ignored_url_count=0, issues=())

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)
        previous_cwd = Path.cwd()
        monkeypatch.chdir(root)
        try:
            assert main([]) == 0
        finally:
            monkeypatch.chdir(previous_cwd)

        assert called is False


def test_cli_jinja_file_prints_ok_jinja():
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\n", encoding="utf-8"
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(jinja_file))
        assert result == "ok"
        assert "ok (jinja)" in buf.getvalue()


def test_cli_check_all_flag_includes_git_dirs():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        git_dir = root / ".git"
        git_dir.mkdir()
        git_file = git_dir / "hidden.yml"
        git_file.write_text("---\nquestion: git\nfield: x\n", encoding="utf-8")
        # --check-all maps to include_default_ignores=False
        collected = _collect_yaml_files([root], include_default_ignores=False)
        assert git_file in collected
        assert process_file(str(git_file)) == "ok"


def test_cli_jinja_file_default_mode_prints_ok_status():
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\n", encoding="utf-8"
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(jinja_file))
        assert result == "ok"
        output = buf.getvalue()
        assert "ok (jinja)" in output
        assert "interview.yml" in output


def test_cli_file_with_errors_reports_error_status():
    """process_file returns 'error' and prints an errors summary line."""
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(bad))
        assert result == "error"
        output = buf.getvalue()
        assert re.search(r"errors \(\d+\):.*bad\.yml", output)
        assert "[E301]" in output


def test_cli_file_with_promoted_errors_reports_error_status():
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
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(warning_file))
        assert result == "error"
        output = buf.getvalue()
        assert re.search(r"errors \(\d+\):.*warning\.yml", output)
        assert "[E410]" in output


def test_parse_ignore_codes_normalizes_comma_separated_codes():
    assert parse_ignore_codes(" e410, E301 ,, c101 ") == frozenset(
        {"E410", "E301", "C101"}
    )


def test_cli_process_file_can_ignore_promoted_error_codes():
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
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(warning_file), ignore_codes=frozenset({"E410"}))
        assert result == "ok"
        output = buf.getvalue()
        assert "ok:" in output
        assert "[E410]" not in output
        assert "warnings (" not in output


def test_cli_file_with_conventions_reports_convention_status():
    with TemporaryDirectory() as tmp:
        convention_file = Path(tmp) / "convention.yml"
        convention_file.write_text(
            "---\n"
            "question: Total fruit\n"
            "fields:\n"
            "  - Apples: number_apples\n"
            "    datatype: integer\n"
            "  - Oranges: number_oranges\n"
            "    datatype: integer\n"
            "validation code: |\n"
            "  if number_apples + number_oranges != 10:\n"
            "    raise Exception('Bad total')\n",
            encoding="utf-8",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(convention_file))
        assert result == "warning"
        output = buf.getvalue()
        assert re.search(r"conventions \(\d+\):.*convention\.yml", output)
        assert "[C101]" in output
        assert "warnings (" not in output
        assert "errors (" not in output


def test_cli_file_with_warnings_reports_warning_status():
    with TemporaryDirectory() as tmp:
        warning_file = Path(tmp) / "warning.yml"
        warning_file.write_text(
            "---\nquestion: Hello\nfield: user_name\n", encoding="utf-8"
        )
        buf = io.StringIO()
        warning = YAMLError(
            err_str="Warning: heads up",
            line_number=2,
            file_name="warning.yml",
        )

        with patch(
            "dayamlchecker.yaml_structure.find_errors_from_string",
            return_value=[warning],
        ):
            with redirect_stdout(buf):
                result = process_file(str(warning_file))

        assert result == "warning"
        output = buf.getvalue()
        assert re.search(r"warnings \(1\):.*warning\.yml", output)
        assert "Warning: heads up" in output
        assert "conventions (" not in output
        assert "errors (" not in output


def test_cli_main_exits_nonzero_when_any_file_has_errors():
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")

        with patch("sys.argv", ["dayamlchecker", str(bad)]):
            assert main() == 1


def test_cli_main_can_ignore_error_codes_from_flag():
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text(
            "---\nquestion: Hello\nquestion: Again\nfield: my_var\n",
            encoding="utf-8",
        )
        buf = io.StringIO()

        with redirect_stdout(buf):
            with patch(
                "sys.argv", ["dayamlchecker", "--ignore-codes", "e101", str(bad)]
            ):
                result = main()

        assert result == 0
        output = buf.getvalue()
        assert output.startswith(".\n")
        assert "[E101]" not in output
        assert "0 errors" in output


def test_cli_main_exits_nonzero_when_file_has_only_promoted_errors():
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
        buf = io.StringIO()

        with redirect_stdout(buf):
            with patch("sys.argv", ["dayamlchecker", str(warning_file)]):
                result = main()

        assert result == 1
        output = buf.getvalue()
        assert "1 errors" in output
        assert "0 warnings" in output


def test_cli_main_reads_ignore_codes_from_parent_pyproject():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
            "[tool.dayaml]\n"
            'ignore_codes = ["E410"]\n',
            encoding="utf-8",
        )
        warning_file = root / "docassemble" / "warning.yml"
        warning_file.parent.mkdir(parents=True)
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
        buf = io.StringIO()

        with redirect_stdout(buf):
            result = main(["--no-url-check", str(warning_file.parent)])

        assert result == 0
        output = buf.getvalue()
        assert output.startswith(".\n")
        assert "[E410]" not in output
        assert "1 ok" in output


def test_cli_main_reads_raw_args_from_pyproject(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
            "[tool.dayaml]\n"
            'args = ["--no-url-check"]\n',
            encoding="utf-8",
        )
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)

        called = False

        def fake_run_url_check(**kwargs):
            nonlocal called
            called = True
            return URLCheckResult(checked_url_count=0, ignored_url_count=0, issues=())

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)

        assert yaml_structure.main([str(root)]) == 0
        assert called is False


def test_cli_args_override_pyproject_raw_args(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
            "[tool.dayaml]\n"
            'args = ["--no-url-check"]\n',
            encoding="utf-8",
        )
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)

        called = False

        def fake_run_url_check(**kwargs):
            nonlocal called
            called = True
            return URLCheckResult(checked_url_count=0, ignored_url_count=0, issues=())

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)

        assert yaml_structure.main(["--url-check", str(root)]) == 0
        assert called is True


def test_cli_jinja_file_with_bad_key_reports_errors():
    """Errors in the Jinja-rendered content must still be caught and reported.

    This is a companion to test_cli_jinja_file_default_mode_prints_ok_status:
    it verifies that the Jinja pre-processing path (preprocess_jinja -> recursive
    find_errors_from_string call) doesn't silently discard validation errors.
    """
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "bad_jinja.yml"
        jinja_file.write_text(
            "# use jinja\n---\nnot_a_real_key: hello\n", encoding="utf-8"
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(jinja_file))
        assert result == "error"
        output = buf.getvalue()
        assert re.search(r"errors \(\d+\).*bad_jinja\.yml", output)
        assert "[E301]" in output


def test_cli_process_file_skips_known_da_files():
    """process_file returns 'skipped' for known DA helper files like docstring.yml."""
    with TemporaryDirectory() as tmp:
        skipped = Path(tmp) / "docstring.yml"
        skipped.write_text(
            "this is not valid yaml interview content\n", encoding="utf-8"
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(skipped))
        assert result == "skipped"
        assert "skipped" in buf.getvalue()


def test_cli_process_file_skipped_uses_line_reporter():
    with TemporaryDirectory() as tmp:
        skipped = Path(tmp) / "docstring.yml"
        skipped.write_text("ignored\n", encoding="utf-8")

        messages: list[str] = []
        result = process_file(str(skipped), line_reporter=messages.append)

        assert result == "skipped"
        assert messages == [f"skipped: {skipped}"]


def test_cli_process_file_quiet_skips_no_output():
    """process_file with quiet=True suppresses output for skipped files."""
    with TemporaryDirectory() as tmp:
        skipped = Path(tmp) / "docstring.yml"
        skipped.write_text("ignored\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(skipped), quiet=True)
        assert result == "skipped"
        assert buf.getvalue() == ""


def test_cli_process_file_quiet_ok_no_output():
    """process_file with quiet=True suppresses output for ok files."""
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(good), quiet=True)
        assert result == "ok"
        assert buf.getvalue() == ""


def test_process_file_format_on_success_prints_reformatted_without_line_reporter():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "format_me.yml"
        _write_valid_code_interview(interview)

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(interview), format_on_success=True)

        assert result == "ok"
        assert (
            interview.read_text(encoding="utf-8")
            == "mandatory: True\ncode: |\n  x = 1\n"
        )
        assert buf.getvalue() == f"reformatted: {interview}\n"


def test_process_file_format_on_success_leaves_already_formatted_file_unchanged():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "already_formatted.yml"
        _write_valid_code_interview(interview, code="x = 1")

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(interview), format_on_success=True)

        assert result == "ok"
        assert (
            interview.read_text(encoding="utf-8")
            == "mandatory: True\ncode: |\n  x = 1\n"
        )
        assert buf.getvalue() == f"ok: {interview}\n"


def test_process_file_warning_uses_line_reporter():
    with TemporaryDirectory() as tmp:
        warning_file = Path(tmp) / "warning.yml"
        warning_file.write_text(
            "---\nquestion: Hello\nfield: user_name\n", encoding="utf-8"
        )
        messages: list[str] = []
        warning = YAMLError(
            err_str="Warning: heads up",
            line_number=2,
            file_name="warning.yml",
        )

        with patch(
            "dayamlchecker.yaml_structure.find_errors_from_string",
            return_value=[warning],
        ):
            result = process_file(str(warning_file), line_reporter=messages.append)

        assert result == "warning"
        assert messages == [f"warnings (1): {warning_file}"]


def test_process_file_format_on_success_warning_prints_reformatted_without_line_reporter():
    with TemporaryDirectory() as tmp:
        convention_file = Path(tmp) / "convention.yml"
        convention_file.write_text(
            "---\n"
            "question: Total fruit\n"
            "fields:\n"
            "  - Apples: number_apples\n"
            "    datatype: integer\n"
            "  - Oranges: number_oranges\n"
            "    datatype: integer\n"
            "validation code: |\n"
            "  if number_apples+number_oranges !=10:\n"
            "    raise Exception('Bad total')\n",
            encoding="utf-8",
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(convention_file), format_on_success=True)

        assert result == "warning"
        assert "if number_apples + number_oranges != 10:" in convention_file.read_text(
            encoding="utf-8"
        )
        output = buf.getvalue()
        assert f"conventions (1): {convention_file}" in output
        assert f"reformatted: {convention_file}" in output


def test_cli_main_no_summary_flag():
    """--no-summary flag suppresses the summary line."""
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("sys.argv", ["dayamlchecker", "--no-summary", str(good)]):
                result = main()
        assert result == 0
        assert "summary" not in buf.getvalue().lower()


def test_cli_main_quiet_flag():
    """--quiet flag suppresses all non-error output."""
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("sys.argv", ["dayamlchecker", "--quiet", str(good)]):
                result = main()
        assert result == 0
        assert buf.getvalue().strip() == ""


def test_main_format_on_success_reformats_ok_file_without_url_check(monkeypatch):
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "format_me.yml"
        _write_valid_code_interview(interview)

        called = False

        def fake_run_url_check(**kwargs):
            nonlocal called
            called = True
            return URLCheckResult(checked_url_count=0, ignored_url_count=0, issues=())

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = main(["--format-on-success", "--no-url-check", str(interview)])

        assert result == 0
        assert called is False
        assert (
            interview.read_text(encoding="utf-8")
            == "mandatory: True\ncode: |\n  x = 1\n"
        )
        output = buf.getvalue()
        assert "reformatted:" in output
        assert "format_me.yml" in output
        assert "Summary: 1 ok" in output


def test_main_format_on_success_reformats_warning_file():
    with TemporaryDirectory() as tmp:
        convention_file = Path(tmp) / "convention.yml"
        convention_file.write_text(
            "---\n"
            "question: Total fruit\n"
            "fields:\n"
            "  - Apples: number_apples\n"
            "    datatype: integer\n"
            "  - Oranges: number_oranges\n"
            "    datatype: integer\n"
            "validation code: |\n"
            "  if number_apples+number_oranges !=10:\n"
            "    raise Exception('Bad total')\n",
            encoding="utf-8",
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = main(
                ["--format-on-success", "--no-url-check", str(convention_file)]
            )

        assert result == 0
        assert "if number_apples + number_oranges != 10:" in convention_file.read_text(
            encoding="utf-8"
        )
        output = buf.getvalue()
        assert result == 0
        assert "conventions (1):" in output
        assert "convention.yml" in output
        assert "reformatted:" in output
        assert "Summary: 0 ok, 1 warnings, 0 errors, 0 skipped" in output


def test_main_format_on_success_does_not_write_yaml_error_file():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "bad.yml"
        original = "mandatory: True\ncode: |\n  x=1\nnot_a_real_key: hello\n"
        interview.write_text(original, encoding="utf-8")

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = main(["--format-on-success", "--no-url-check", str(interview)])

        assert result == 1
        assert interview.read_text(encoding="utf-8") == original
        output = buf.getvalue()
        assert "errors (1):" in output
        assert "bad.yml" in output
        assert "reformatted:" not in output


def test_main_format_on_success_respects_ignore_codes():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "ignored.yml"
        interview.write_text(
            "mandatory: True\ncode: |\n  x=1\nnot_a_real_key: hello\n",
            encoding="utf-8",
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = main(
                [
                    "--format-on-success",
                    "--no-url-check",
                    "--ignore-codes",
                    "E301",
                    str(interview),
                ]
            )

        assert result == 0
        assert interview.read_text(encoding="utf-8").startswith(
            "mandatory: True\ncode: |\n  x = 1\n"
        )
        output = buf.getvalue()
        assert "reformatted:" in output
        assert "ignored.yml" in output
        assert "[E301]" not in output


def test_main_format_on_success_writes_before_url_checker_error(monkeypatch, capsys):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_code_interview(interview)

        def fake_run_url_check(**kwargs):
            return URLCheckResult(
                checked_url_count=1,
                ignored_url_count=0,
                issues=(
                    URLIssue(
                        severity="error",
                        category="broken",
                        source_kind="yaml",
                        url="https://example.invalid/question",
                        sources=("docassemble/Demo/data/questions/test.yml",),
                        status_code=404,
                    ),
                ),
            )

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)

        assert main(["--format-on-success", str(interview)]) == 1
        assert (
            interview.read_text(encoding="utf-8")
            == "mandatory: True\ncode: |\n  x = 1\n"
        )

        output = capsys.readouterr().out
        assert "reformatted:" in output
        assert "test.yml" in output
        assert "url checker errors:" in output.lower()


def test_cli_main_summary_shows_counts():
    """Summary line shows counts for ok, errors, skipped."""
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("sys.argv", ["dayamlchecker", str(good)]):
                main()
        output = buf.getvalue()
        assert "Summary:" in output
        assert "1 ok" in output


def test_cli_main_summary_counts_skipped_files():
    with TemporaryDirectory() as tmp:
        skipped = Path(tmp) / "good.yml"
        skipped.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch(
                "dayamlchecker.yaml_structure.process_file", return_value="skipped"
            ):
                with patch("sys.argv", ["dayamlchecker", str(skipped)]):
                    result = main()

        assert result == 0
        assert "1 skipped" in buf.getvalue()


def test_cli_main_summary_counts_warning_files():
    with TemporaryDirectory() as tmp:
        warning_file = Path(tmp) / "warning.yml"
        warning_file.write_text(
            "---\nquestion: Hello\nfield: user_name\n", encoding="utf-8"
        )
        buf = io.StringIO()

        with redirect_stdout(buf):
            with patch(
                "dayamlchecker.yaml_structure.process_file", return_value="warning"
            ):
                result = main(["--no-url-check", str(warning_file)])

        assert result == 0
        assert "1 warnings" in buf.getvalue()


def test_cli_display_falls_back_to_absolute_path_when_not_under_base():
    with TemporaryDirectory() as base_tmp, TemporaryDirectory() as other_tmp:
        base = Path(base_tmp)
        outside = Path(other_tmp) / "outside.yml"
        outside.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()

        with redirect_stdout(buf):
            with patch(
                "dayamlchecker.yaml_structure._collect_yaml_files",
                return_value=[outside],
            ):
                with patch("sys.argv", ["dayamlchecker", str(base)]):
                    result = main()

        assert result == 0
        assert buf.getvalue().startswith(".\n")


def test_cli_display_prefers_path_relative_to_cwd(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        scan_dir = root / "docassemble"
        interview = scan_dir / "WorkflowDocs" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)
        buf = io.StringIO()

        previous_cwd = Path.cwd()
        monkeypatch.chdir(root)
        try:
            with redirect_stdout(buf):
                result = main(["--no-url-check", str(scan_dir)])
        finally:
            monkeypatch.chdir(previous_cwd)

        assert result == 0
        assert buf.getvalue().startswith(".\n")


def test_cli_main_no_summary_still_ends_dot_line():
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()

        with redirect_stdout(buf):
            result = main(["--no-summary", "--no-url-check", str(good)])

        assert result == 0
        assert buf.getvalue() == ".\n"


def test_cli_display_path_used_in_output():
    """process_file uses display_path when provided."""
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(good), display_path="custom/path.yml")
        assert result == "ok"
        assert "custom/path.yml" in buf.getvalue()


def test_cli_default_omits_real_error_prefix():
    """process_file omits the REAL ERROR prefix by default on non-experimental errors."""
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = process_file(str(bad))
        assert result == "error"
        output = buf.getvalue()
        assert "[E301]" in output
        assert "REAL ERROR" not in output


def test_cli_show_experimental_flag_via_main():
    """--show-experimental adds the REAL ERROR prefix through the main() entry point."""
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("sys.argv", ["dayamlchecker", "--show-experimental", str(bad)]):
                main()
        output = buf.getvalue()
        assert "[E301]" in output
        assert "REAL ERROR" in output


def test_cli_no_show_experimental_flag_via_main():
    """--no-show-experimental explicitly suppresses the REAL ERROR prefix."""
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch(
                "sys.argv", ["dayamlchecker", "--no-show-experimental", str(bad)]
            ):
                main()
        output = buf.getvalue()
        assert "[E301]" in output
        assert "REAL ERROR" not in output


def test_package_main_aliases_yaml_structure_main():
    """The package entrypoint should directly expose the checker CLI main."""
    assert package_main is main


def test_main_default_wcag_reports_errors_and_fails():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "accessibility.yml"
        interview.write_text(
            "question: |\n  ![](docassemble.demo:data/static/logo.png)\n",
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(interview)])

        output = stdout.getvalue().lower()
        assert exit_code == 1
        assert "errors (1)" in output
        assert "[e505]" in output
        assert "accessibility: markdown image" in output


def test_main_wcag_accessibility_error_fails():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "tagged-pdf-warning.yml"
        interview.write_text(
            "attachments:\n"
            "  - name: My attachment\n"
            "    docx template file: demo_template.docx\n",
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(interview)])

        output = stdout.getvalue().lower()
        assert exit_code == 1
        assert "errors (1)" in output
        assert "[e503]" in output
        assert "accessibility: docx attachment detected" in output


def test_main_promoted_error_only_file_fails():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "warning.yml"
        interview.write_text(
            "question: |\n"
            "  Dynamic fields\n"
            "fields:\n"
            "  - code: |\n"
            "      [\n"
            '        {"field": "other_parties[0].vacated", "label": "P1", "datatype": "yesno"}\n'
            "      ]\n"
            "  - label: Vacated date\n"
            "    field: vacated_date\n"
            "    datatype: date\n"
            "    js show if: |\n"
            '      val("other_parties[0].vacated")\n',
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--no-wcag", str(interview)])

        output = stdout.getvalue().lower()
        assert exit_code == 1
        assert "errors (" in output


def test_main_combobox_widget_check_disabled_by_default():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "combobox.yml"
        interview.write_text(
            "question: |\n  Pick one\ncombobox: selected_option\n",
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--no-url-check", str(interview)])

        output = stdout.getvalue().lower()
        assert exit_code == 0
        assert "screen uses `combobox`" not in output


def test_main_can_enable_combobox_widget_error():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "combobox.yml"
        interview.write_text(
            "question: |\n  Pick one\ncombobox: selected_option\n",
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "--no-url-check",
                    "--accessibility-error-on-widget",
                    "combobox",
                    str(interview),
                ]
            )

        output = stdout.getvalue().lower()
        assert exit_code == 1
        assert "errors (1)" in output
        assert "[e501]" in output
        assert "screen uses `combobox`" in output


def test_main_invokes_url_checker_with_default_severities(monkeypatch, capsys):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)

        captured: dict[str, object] = {}

        def fake_run_url_check(**kwargs):
            captured.update(kwargs)
            return URLCheckResult(
                checked_url_count=1,
                ignored_url_count=0,
                issues=(
                    URLIssue(
                        severity="warning",
                        category="broken",
                        source_kind="template",
                        url="https://example.invalid/document",
                        sources=("docassemble/Demo/data/templates/notice.docx",),
                        status_code=404,
                    ),
                ),
            )

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)
        monkeypatch.setattr(
            sys,
            "argv",
            ["dayamlchecker", str(interview)],
        )

        assert yaml_structure.main() == 0
        assert captured["root"] == root.resolve()
        assert captured["question_files"] == [interview]
        assert captured["package_dirs"] == [(root / "docassemble" / "Demo").resolve()]
        assert captured["timeout"] == 10
        assert captured["check_documents"] is True
        assert captured["ignore_urls"] == set()
        assert captured["yaml_severity"] == "error"
        assert captured["document_severity"] == "warning"
        assert captured["unreachable_severity"] == "warning"

        out = capsys.readouterr().out
        assert "url checker warnings:" in out.lower()
        assert "question files" not in out


def test_main_can_disable_url_checker(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)

        called = False

        def fake_run_url_check(**kwargs):
            nonlocal called
            called = True
            return URLCheckResult(checked_url_count=0, ignored_url_count=0, issues=())

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)
        monkeypatch.setattr(
            sys,
            "argv",
            ["dayamlchecker", "--no-url-check", str(interview)],
        )

        assert yaml_structure.main() == 0
        assert called is False


def test_main_fails_on_url_checker_errors(monkeypatch, capsys):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)

        def fake_run_url_check(**kwargs):
            return URLCheckResult(
                checked_url_count=1,
                ignored_url_count=0,
                issues=(
                    URLIssue(
                        severity="error",
                        category="broken",
                        source_kind="yaml",
                        url="https://example.invalid/question",
                        sources=("docassemble/Demo/data/questions/test.yml",),
                        status_code=404,
                    ),
                ),
            )

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)
        monkeypatch.setattr(
            sys,
            "argv",
            ["dayamlchecker", str(interview)],
        )

        assert yaml_structure.main() == 1
        out = capsys.readouterr().out
        assert "url checker errors:" in out.lower()
        assert "question files" in out


def test_main_passes_custom_url_checker_flags(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "docassemble" / "Demo" / "data" / "questions" / "test.yml"
        _write_valid_question(interview)

        captured: dict[str, object] = {}

        def fake_run_url_check(**kwargs):
            captured.update(kwargs)
            return URLCheckResult(checked_url_count=0, ignored_url_count=0, issues=())

        monkeypatch.setattr(yaml_structure, "run_url_check", fake_run_url_check)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dayamlchecker",
                "--url-check-root",
                str(root),
                "--url-check-timeout",
                "3",
                "--url-check-ignore-urls",
                "https://ignore.example/path",
                "--url-check-skip-templates",
                "--template-url-severity",
                "ignore",
                "--unreachable-url-severity",
                "error",
                str(interview),
            ],
        )

        assert yaml_structure.main() == 0
        assert captured["root"] == root.resolve()
        assert captured["timeout"] == 3
        assert captured["check_documents"] is False
        assert captured["ignore_urls"] == {"https://ignore.example/path"}
        assert captured["yaml_severity"] == "error"
        assert captured["document_severity"] == "ignore"
        assert captured["unreachable_severity"] == "error"
