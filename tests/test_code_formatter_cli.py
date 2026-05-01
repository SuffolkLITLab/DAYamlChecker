import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests._cli_helpers import RunResult

from dayamlchecker._files import _collect_yaml_files
from dayamlchecker.code_formatter import main


def test_formatter_collect_yaml_files_default_ignores_common_directories():
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


def test_formatter_collect_yaml_files_can_disable_default_ignores():
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


def test_formatter_collect_yaml_files_skips_ignored_root_directory_itself():
    with TemporaryDirectory() as tmp:
        git_root = Path(tmp) / ".git"
        git_root.mkdir()
        hidden = git_root / "hidden.yml"
        hidden.write_text("question: git\n", encoding="utf-8")

        collected = _collect_yaml_files([git_root])

        assert collected == []


def _run_formatter(*args: str) -> RunResult:
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with patch("sys.argv", ["dayamlchecker.code_formatter", *args]):
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            returncode = main()
    return RunResult(returncode, stdout_buf.getvalue(), stderr_buf.getvalue())


def test_formatter_skips_jinja_file_with_message():
    """A Jinja file with no code blocks should still be handled without error."""
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\n", encoding="utf-8"
        )

        result = _run_formatter(str(jinja_file))

        assert result.returncode == 0


def test_formatter_jinja_count_in_summary():
    """A Jinja file with a clean (non-Jinja) code block is counted as reformatted."""
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\ncode: |\n  x=1\n",
            encoding="utf-8",
        )

        result = _run_formatter(str(jinja_file))

        assert "1 reformatted" in result.stdout
        assert "skipped (Jinja)" not in result.stdout


def test_formatter_jinja_not_in_summary_when_zero():
    """The old 'skipped (Jinja)' label should never appear in output."""
    with TemporaryDirectory() as tmp:
        regular_file = Path(tmp) / "interview.yml"
        regular_file.write_text("---\nquestion: Hello world\n", encoding="utf-8")

        result = _run_formatter(str(regular_file))

        assert "skipped (Jinja)" not in result.stdout


def test_formatter_jinja_file_with_clean_code_is_formatted():
    """A Jinja file whose code block has no Jinja syntax should be formatted."""
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        original = "# use jinja\n---\nquestion: Hello {{ user }}\ncode: |\n  x=1\n"
        jinja_file.write_text(original, encoding="utf-8")

        result = _run_formatter(str(jinja_file))

        assert result.returncode == 0
        assert "reformatted" in result.stdout
        formatted = jinja_file.read_text(encoding="utf-8")
        assert "x = 1" in formatted
        assert "{{ user }}" in formatted
        assert formatted.startswith("# use jinja\n")


def test_formatter_jinja_file_already_formatted_unchanged():
    """A Jinja file with already-formatted code should be reported unchanged."""
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        original = "# use jinja\n---\nquestion: Hello {{ user }}\ncode: |\n  x = 1\n"
        jinja_file.write_text(original, encoding="utf-8")

        result = _run_formatter(str(jinja_file))

        assert result.returncode == 0
        assert "unchanged" in result.stdout
        assert jinja_file.read_text(encoding="utf-8") == original


def test_formatter_jinja_file_with_jinja_in_code_block_not_modified():
    """A code block that itself contains Jinja syntax must not be touched."""
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        original = (
            "# use jinja\n"
            "---\n"
            "code: |\n"
            "  {% for item in items %}\n"
            "  x = {{ item }}\n"
            "  {% endfor %}\n"
        )
        jinja_file.write_text(original, encoding="utf-8")

        result = _run_formatter(str(jinja_file))

        assert result.returncode == 0
        assert jinja_file.read_text(encoding="utf-8") == original


def test_formatter_quiet_suppresses_output():
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\n", encoding="utf-8"
        )

        result = _run_formatter("--quiet", str(jinja_file))

        assert result.returncode == 0
        # quiet suppresses all normal output
        assert result.stdout.strip() == ""


def test_formatter_quiet_suppresses_reformatted_output_too():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "interview.yml"
        interview.write_text("---\ncode: |\n  x=1\n", encoding="utf-8")

        result = _run_formatter("--quiet", str(interview))

        assert result.returncode == 0
        assert result.stdout.strip() == ""
        assert interview.read_text(encoding="utf-8") == "---\ncode: |\n  x = 1\n"


def test_formatter_summary_shows_unchanged_for_already_formatted_jinja():
    """A Jinja file with already-formatted code blocks appears as 'unchanged'."""
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\n", encoding="utf-8"
        )

        result = _run_formatter(str(jinja_file))

        assert "unchanged" in result.stdout
        assert "skipped (Jinja)" not in result.stdout


def test_formatter_jinja_without_header_is_processed_as_plain_yaml():
    """A file with '{{ }}' and no header is handled through the normal YAML path."""
    with TemporaryDirectory() as tmp:
        bad_file = Path(tmp) / "interview.yml"
        original = "---\nquestion: Hello {{ user }}\n"
        bad_file.write_text(original, encoding="utf-8")

        result = _run_formatter(str(bad_file))

        assert result.returncode == 0
        assert result.stderr.strip() == ""
        assert "unchanged" in result.stdout
        assert bad_file.read_text(encoding="utf-8") == original


def test_formatter_jinja_without_header_with_code_block_is_formatted():
    """Without the header, valid YAML still gets normal code formatting."""
    with TemporaryDirectory() as tmp:
        bad_file = Path(tmp) / "interview.yml"
        original = "---\nquestion: Hello {{ user }}\ncode: |\n  x=1\n"
        bad_file.write_text(original, encoding="utf-8")

        result = _run_formatter(str(bad_file))

        assert result.returncode == 0
        assert "reformatted" in result.stdout
        assert bad_file.read_text(encoding="utf-8") == (
            "---\nquestion: Hello {{ user }}\ncode: |\n  x = 1\n"
        )


def test_formatter_no_yaml_files_found():
    """main() returns 1 and prints error when no YAML files are found."""
    with TemporaryDirectory() as tmp:
        txt = Path(tmp) / "readme.txt"
        txt.write_text("not yaml\n", encoding="utf-8")
        result = _run_formatter(str(txt))
        assert result.returncode == 1
        assert "no yaml files found" in result.stderr.lower()


def test_formatter_display_uses_absolute_path_for_file_outside_bases():
    with TemporaryDirectory() as base_tmp, TemporaryDirectory() as other_tmp:
        base = Path(base_tmp)
        outside = Path(other_tmp) / "outside.yml"
        outside.write_text("---\ncode: |\n  x = 1\n", encoding="utf-8")

        with patch(
            "dayamlchecker.code_formatter._collect_yaml_files", return_value=[outside]
        ):
            result = _run_formatter(str(base))

        assert result.returncode == 0
        assert str(outside.resolve()) in result.stdout


def test_formatter_display_prefers_path_relative_to_cwd(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        scan_dir = root / "docassemble"
        interview = scan_dir / "WorkflowDocs" / "data" / "questions" / "test.yml"
        interview.parent.mkdir(parents=True, exist_ok=True)
        interview.write_text("---\ncode: |\n  x = 1\n", encoding="utf-8")

        previous_cwd = Path.cwd()
        monkeypatch.chdir(root)
        try:
            result = _run_formatter(str(scan_dir))
        finally:
            monkeypatch.chdir(previous_cwd)

        assert result.returncode == 0
        assert (
            "unchanged: docassemble/WorkflowDocs/data/questions/test.yml"
            in result.stdout
        )


def test_formatter_check_mode_does_not_write():
    """--check reports files that would change but doesn't modify them."""
    with TemporaryDirectory() as tmp:
        f = Path(tmp) / "interview.yml"
        original = "---\ncode: |\n  x=1\n"
        f.write_text(original, encoding="utf-8")

        result = _run_formatter("--check", str(f))

        assert result.returncode == 1
        assert "would reformat" in result.stdout.lower()
        assert f.read_text(encoding="utf-8") == original


def test_formatter_check_mode_unchanged_exits_zero():
    """--check returns 0 when no formatting changes are needed."""
    with TemporaryDirectory() as tmp:
        f = Path(tmp) / "interview.yml"
        f.write_text("---\ncode: |\n  x = 1\n", encoding="utf-8")

        result = _run_formatter("--check", str(f))

        assert result.returncode == 0


def test_formatter_no_summary_flag():
    """--no-summary suppresses the summary line."""
    with TemporaryDirectory() as tmp:
        f = Path(tmp) / "interview.yml"
        f.write_text("---\ncode: |\n  x = 1\n", encoding="utf-8")

        result = _run_formatter("--no-summary", str(f))

        assert result.returncode == 0
        assert "summary" not in result.stdout.lower()


def test_formatter_file_not_found_reports_error():
    """A non-existent file path is reported as an error in stderr."""
    with TemporaryDirectory() as tmp:
        # Do not create the file; pass a path that doesn't exist to the CLI.
        missing = Path(tmp) / "missing.yml"

        result = _run_formatter(str(missing))

        # The formatter should fail and report the error on stderr.
        assert result.returncode != 0
        assert "error" in result.stderr.lower()


def test_formatter_summary_shows_error_count():
    """Summary includes error count when a file causes an exception."""
    with TemporaryDirectory() as tmp:
        # Create a binary file with .yml extension that can't be decoded
        bad = Path(tmp) / "bad.yml"
        bad.write_bytes(b"\x80\x81\x82\x83")

        result = _run_formatter(str(bad))

        assert result.returncode == 1
        assert "error" in result.stderr.lower() or "error" in result.stdout.lower()
