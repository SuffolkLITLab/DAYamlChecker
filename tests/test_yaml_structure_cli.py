from pathlib import Path
from tempfile import TemporaryDirectory

from dayamlchecker.yaml_structure import _collect_yaml_files


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
