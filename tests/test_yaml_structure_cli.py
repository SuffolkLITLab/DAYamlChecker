import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import dayamlchecker.yaml_structure as yaml_structure
from dayamlchecker.check_questions_urls import URLCheckResult, URLIssue
from dayamlchecker.yaml_structure import _collect_yaml_files


def _write_valid_question(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "question: |\n  What is your name?\nfield: user_name\n",
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
        assert captured["root"] == root
        assert captured["question_files"] == [interview]
        assert captured["package_dirs"] == [root / "docassemble" / "Demo"]
        assert captured["timeout"] == 10
        assert captured["check_documents"] is True
        assert captured["ignore_urls"] == set()
        assert captured["yaml_severity"] == "error"
        assert captured["document_severity"] == "warning"
        assert captured["unreachable_severity"] == "warning"

        out = capsys.readouterr().out
        assert "URL checker warnings:" in out
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
        assert "URL checker errors:" in out
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
        assert captured["root"] == root
        assert captured["timeout"] == 3
        assert captured["check_documents"] is False
        assert captured["ignore_urls"] == {"https://ignore.example/path"}
        assert captured["yaml_severity"] == "error"
        assert captured["document_severity"] == "ignore"
        assert captured["unreachable_severity"] == "error"
