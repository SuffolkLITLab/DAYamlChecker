import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dayamlchecker.yaml_structure import _collect_yaml_files, main, process_file


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
        sources_file = root / "sources" / "skip.yml"

        git_file.parent.mkdir(parents=True)
        github_file.parent.mkdir(parents=True)
        sources_file.parent.mkdir(parents=True)

        visible.write_text("question: visible\n", encoding="utf-8")
        git_file.write_text("question: git\n", encoding="utf-8")
        github_file.write_text("question: github\n", encoding="utf-8")
        sources_file.write_text("question: sources\n", encoding="utf-8")

        collected = _collect_yaml_files([root])

        assert collected == [visible]


def test_collect_yaml_files_can_disable_default_ignores():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        visible = root / "visible.yml"
        git_file = root / ".git" / "hidden.yml"
        github_file = root / ".github-actions" / "ci.yml"
        sources_file = root / "sources" / "skip.yml"

        git_file.parent.mkdir(parents=True)
        github_file.parent.mkdir(parents=True)
        sources_file.parent.mkdir(parents=True)

        visible.write_text("question: visible\n", encoding="utf-8")
        git_file.write_text("question: git\n", encoding="utf-8")
        github_file.write_text("question: github\n", encoding="utf-8")
        sources_file.write_text("question: sources\n", encoding="utf-8")

        collected = _collect_yaml_files([root], include_default_ignores=False)

        assert collected == sorted([visible, git_file, github_file, sources_file])


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
        assert re.search(r"errors \(\d+\):.*bad\.yml", buf.getvalue())


def test_cli_main_exits_nonzero_when_any_file_has_errors():
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")

        with patch("sys.argv", ["dayamlchecker", str(bad)]):
            assert main() == 1


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
        assert re.search(r"errors \(\d+\).*bad_jinja\.yml", buf.getvalue())
