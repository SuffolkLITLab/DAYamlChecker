import io
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout

from dayamlchecker.yaml_structure import _collect_yaml_files, main


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


def test_main_accessibility_lint_mode_reports_failures():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        interview = root / "accessibility.yml"
        interview.write_text(
            "question: |\n  ![](docassemble.demo:data/static/logo.png)\n",
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--wcag", str(interview)])

        output = stdout.getvalue().lower()
        assert exit_code == 1
        assert "found 1 errors" in output
        assert "accessibility: markdown image" in output


def test_main_wcag_warning_only_does_not_fail():
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
            exit_code = main(["--wcag", str(interview)])

        output = stdout.getvalue().lower()
        assert exit_code == 0
        assert "warning: accessibility: docx attachment detected" in output
