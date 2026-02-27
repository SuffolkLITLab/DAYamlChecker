import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from dayamlchecker.yaml_structure import _collect_yaml_files


def _run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "dayamlchecker.yaml_structure", *args],
        capture_output=True,
        text=True,
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
# CLI (main()) integration tests
# ---------------------------------------------------------------------------


def test_cli_valid_file_exits_zero():
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.yml"
        good.write_text("---\nquestion: Hello\nfield: my_var\n", encoding="utf-8")
        result = _run_checker(str(good))
        assert result.returncode == 0


def test_cli_no_files_found_exits_nonzero():
    with TemporaryDirectory() as tmp:
        # Write a text file, not YAML
        txt = Path(tmp) / "readme.txt"
        txt.write_text("hello\n", encoding="utf-8")
        result = _run_checker(str(txt))
        assert result.returncode == 1


def test_cli_jinja_file_prints_j():
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\n", encoding="utf-8"
        )
        result = _run_checker(str(jinja_file))
        assert result.returncode == 0
        assert "j" in result.stdout


def test_cli_check_all_flag_includes_git_dirs():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        git_dir = root / ".git"
        git_dir.mkdir()
        git_file = git_dir / "hidden.yml"
        git_file.write_text("---\nquestion: git\nfield: x\n", encoding="utf-8")
        result = _run_checker("--check-all", str(root))
        # Should not exit 1 just because of the .git dir being present
        # (the file itself is valid so returncode 0 expected)
        assert result.returncode == 0


def test_cli_verbose_flag_prints_rendered_yaml():
    with TemporaryDirectory() as tmp:
        jinja_file = Path(tmp) / "interview.yml"
        jinja_file.write_text(
            "# use jinja\n---\nquestion: Hello {{ user }}\n", encoding="utf-8"
        )
        result = _run_checker("--verbose", str(jinja_file))
        assert result.returncode == 0
        assert "Jinja-rendered output" in result.stdout


def test_cli_file_with_errors_still_exits_zero():
    """yaml_structure main() currently always returns 0 even with errors."""
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.yml"
        bad.write_text("---\nnot_a_real_key: hello\n", encoding="utf-8")
        result = _run_checker(str(bad))
        # Current behaviour: exits 0 regardless
        assert result.returncode == 0
        assert "Found" in result.stdout
