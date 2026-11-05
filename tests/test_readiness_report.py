import copy
import json

import pytest

from dayamlchecker import readiness
from dayamlchecker.readiness_report import markdown_report, main as render_main
from dayamlchecker.yaml_structure import main


def report():
    return {
        "root": "/repo/demo",
        "status": "needs_review",
        "source_sha256": "abc",
        "checks": [{"id": "github_publication", "status": "not_checked"}],
        "findings": [],
        "research": None,
        "review": {
            "actionable": [],
            "cleanup": [],
            "coverage": [],
            "process_evidence": [{"id": "legal_review", "status": "needs_review"}],
        },
    }


def test_no_findings_is_not_approval_and_missing_signoff_is_not_defect():
    r = report()
    original = copy.deepcopy(r)
    text = markdown_report(r)
    assert "No automated publication blocker" in text
    assert "Instructor review is still needed" in text
    assert "research was not run" in text
    assert "missing sign-offs, not additional defects" in text
    assert "not checked" in text
    assert "Fix the automated blockers" not in text
    assert r == original


def test_research_evidence_stays_provisional_and_failed_coverage_visible():
    r = report()
    r["research"] = {
        "execution_status": "incomplete",
        "model": "test-model",
        "coverage_gaps": ["One file was truncated"],
        "findings": [
            {
                "local_quote": "Write only to the court",
                "failure_example": "Caretaker is never notified",
                "affected_users": "People cancelling the form",
                "baseline_reason": "Added instruction",
                "source_urls": ["https://example.com/source", "javascript:bad()"],
            }
        ],
    }
    r["review"]["actionable"] = [
        {
            "source": "research",
            "finding_indexes": [0],
            "file": "steps.docx",
            "message": "Correct the cancellation steps.",
            "release_gate": False,
        }
    ]
    text = markdown_report(r)
    assert "AI research suggestion" in text
    for evidence in [
        "Write only to the court",
        "Caretaker is never notified",
        "Added instruction",
        "People cancelling",
        "One file was truncated",
        "https://example.com/source",
    ]:
        assert evidence in text
    assert "javascript:" not in text
    assert "Fix the automated blockers" not in text
    assert "not a clean result" in text
    r["research"].update(execution_status="failed", error="Provider timed out")
    assert "Provider timed out" in markdown_report(r)


def test_blocker_cleanup_and_source_fences_are_preserved():
    r = report()
    r["findings"] = [
        {
            "code": "ER123",
            "context": {
                "repair_context": {
                    "source_yaml": "question: |\n  ```\n  <script>bad</script>"
                }
            },
        }
    ]
    r["review"]["actionable"] = [
        {
            "source": "static",
            "finding_indexes": [0],
            "message": "Fix syntax",
            "release_gate": True,
        }
    ]
    r["review"]["cleanup"] = [
        {
            "source": "static",
            "finding_indexes": [],
            "message": "<script>optional</script>",
            "reason": "Only a convention",
        }
    ]
    text = markdown_report(r)
    assert "Fix the automated blockers" in text
    assert "- [ ] **1.** Fix syntax" in text
    assert "````text" in text
    assert "&lt;script&gt;optional&lt;/script&gt;" in text
    assert "Optional improvements — not publication requirements" in text


@pytest.mark.parametrize("entry", [main, readiness.main])
def test_both_cli_paths_render_markdown_keep_exit_status(
    tmp_path, monkeypatch, capsys, entry
):
    monkeypatch.setattr(readiness, "publication_readiness", lambda *a, **k: report())
    args = [str(tmp_path), "--readiness-format", "markdown"]
    if entry is main:
        args.append("--readiness")
    assert entry(args) == 2
    assert "# Publication review: demo" in capsys.readouterr().out


def test_saved_report_rendering_and_research_only_rejection(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report()))
    assert render_main([str(path)]) == 0
    assert "Instructor decision" in capsys.readouterr().out
    path.write_text('{"findings": []}')
    with pytest.raises(SystemExit) as exc:
        render_main([str(path)])
    assert exc.value.code == 2


def test_playground_errors_and_projects_render_without_implied_github_publication():
    text = markdown_report(
        {
            "source": "docassemble_playground",
            "projects": [
                {"project": "One", "report": report()},
                {"project": "Two", "error": "Download failed"},
                {"project": "Three", "detail": "No question YAML in this project."},
            ],
        }
    )
    assert "GitHub publication has not been verified" in text
    assert "Download failed" in text
    assert "No question YAML" in text
    assert "Project: One" in text


def test_markdown_format_requires_readiness():
    with pytest.raises(SystemExit) as exc:
        main([".", "--readiness-format", "markdown"])
    assert exc.value.code == 2
