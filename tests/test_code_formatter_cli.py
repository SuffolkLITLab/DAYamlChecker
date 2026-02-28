import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from dayamlchecker.code_formatter import _collect_yaml_files


def test_formatter_collect_yaml_files_default_ignores_common_directories():
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


def test_formatter_collect_yaml_files_can_disable_default_ignores():
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


def _run_formatter(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "dayamlchecker.code_formatter", *args],
        capture_output=True,
        text=True,
    )


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


def test_formatter_jinja_without_header_is_error():
    """A file with Jinja syntax but no '# use jinja' header should be flagged as an error."""
    with TemporaryDirectory() as tmp:
        bad_file = Path(tmp) / "interview.yml"
        original = "---\nquestion: Hello {{ user }}\n"
        bad_file.write_text(original, encoding="utf-8")

        result = _run_formatter(str(bad_file))

        assert result.returncode == 1
        assert "error" in result.stderr
        assert "# use jinja" in result.stderr
        assert bad_file.read_text(encoding="utf-8") == original


def test_formatter_jinja_without_header_not_modified():
    """A file incorrectly containing Jinja syntax must not be modified."""
    with TemporaryDirectory() as tmp:
        bad_file = Path(tmp) / "interview.yml"
        original = "---\nquestion: Hello {{ user }}\ncode: |\n  x=1\n"
        bad_file.write_text(original, encoding="utf-8")

        _run_formatter(str(bad_file))

        assert bad_file.read_text(encoding="utf-8") == original
