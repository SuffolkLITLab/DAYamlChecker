from pathlib import Path
from tempfile import TemporaryDirectory

from dayamlchecker.code_formatter import _collect_yaml_files


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
