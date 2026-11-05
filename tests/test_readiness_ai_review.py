import copy
import json
from pathlib import Path

import pytest

from dayamlchecker import readiness, readiness_ai_review as ai
from dayamlchecker.readiness_report import markdown_report
from dayamlchecker.yaml_structure import main


def sample():
    return {
        "root": "/repo",
        "source_sha256": "revision",
        "status": "needs_review",
        "checks": [],
        "findings": [{"code": "IS724", "message": "Missing edits", "context": {}}],
        "research": None,
        "local_scope": {"active_local_files": ["main.yml"], "entrypoints": []},
        "review": {
            "actionable": [
                {
                    "source": "static",
                    "file": "main.yml",
                    "message": "Missing edits",
                    "finding_indexes": [0],
                    "priority": "medium",
                    "release_gate": False,
                }
            ],
            "cleanup": [],
            "coverage": [],
            "process_evidence": [],
            "defect_status": "review_candidates",
        },
    }


@pytest.fixture
def material(monkeypatch):
    monkeypatch.setattr(
        ai,
        "collect_material",
        lambda *a: {
            "documents": [
                {
                    "file": "main.yml",
                    "text": "review:\n  - Edit: children.revisit\nquestion: Review your answers",
                }
            ],
            "coverage_gaps": [],
        },
    )


def provider(monkeypatch, mode="dismiss", bad=None):
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs)
        request = kwargs["json"]
        assert "tools" not in request and request["store"] is False
        data = json.loads(request["input"])
        decision = {
            "id": data["candidates"][0]["id"],
            "decision": mode,
            "message": "Keep the existing child edit link.",
            "reason": "The review already links to this screen.",
            "evidence_document_id": data["documents"][0]["id"],
            "evidence_quote": "Edit: children.revisit",
        }
        decisions = [decision]
        if bad == "quote":
            decision["evidence_quote"] = "Invented counterevidence"
        if bad == "id":
            decision["id"] = "unknown"
        if bad == "duplicate":
            decisions.append(decision)
        if bad == "missing":
            decisions = []
        if bad == "uncertain":
            decision.update(
                decision="uncertain", evidence_document_id="", evidence_quote=""
            )

        class Response:
            ok = True

            def json(self):
                return {
                    "status": "completed",
                    "usage": {"input_tokens": 10},
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"decisions": decisions}),
                                }
                            ],
                        }
                    ],
                }

        return Response()

    monkeypatch.setattr(ai.requests, "post", post)
    return calls


def test_precision_keeps_originals_status_and_reviewer_counterevidence(
    monkeypatch, material
):
    r = sample()
    original = copy.deepcopy(r)
    calls = provider(monkeypatch)
    r["ai_review"] = ai.review_candidates(
        r, Path("/repo"), ai.AIReviewOptions(api_key="test")
    )
    assert r["ai_review"]["execution_status"] == "completed"
    ai.apply_ai_review(r)
    assert len(calls) == 1
    assert r["ai_review"]["decisions"][0]["evidence_file"] == "main.yml"
    assert r["review"]["actionable"] == []
    assert r["review_unfiltered"] == original["review"]
    assert r["findings"] == original["findings"] and r["status"] == original["status"]
    text = markdown_report(r)
    assert (
        "set aside" in text
        and "Missing edits" in text
        and "Edit: children.revisit" in text
    )


@pytest.mark.parametrize("bad", ["quote", "id", "duplicate", "missing"])
def test_invalid_review_does_not_hide_any_candidates(monkeypatch, material, bad):
    r = sample()
    original = copy.deepcopy(r["review"])
    provider(monkeypatch, bad=bad)
    r["ai_review"] = ai.review_candidates(
        r, Path("/repo"), ai.AIReviewOptions(api_key="test")
    )
    assert r["ai_review"]["execution_status"] == "failed"
    ai.apply_ai_review(r)
    assert r["review"] == original


def test_uncertain_stays_visible_and_advisory_moves_to_cleanup(monkeypatch, material):
    for mode in ["uncertain", "advisory"]:
        r = sample()
        provider(
            monkeypatch, mode=mode, bad="uncertain" if mode == "uncertain" else None
        )
        r["ai_review"] = ai.review_candidates(
            r, Path("/repo"), ai.AIReviewOptions(api_key="test")
        )
        ai.apply_ai_review(r)
        assert len(r["review"]["actionable" if mode == "uncertain" else "cleanup"]) == 1


def test_blockers_are_not_sent_or_downgraded(monkeypatch, material):
    r = sample()
    r["review"]["actionable"][0]["release_gate"] = True
    monkeypatch.setattr(
        ai.requests, "post", lambda *a, **k: pytest.fail("No call for hard blockers")
    )
    result = ai.review_candidates(r, Path("/repo"), ai.AIReviewOptions(api_key="test"))
    assert result["execution_status"] == "not_needed"


def test_stale_review_does_not_apply(monkeypatch, material):
    r = sample()
    provider(monkeypatch)
    r["ai_review"] = ai.review_candidates(
        r, Path("/repo"), ai.AIReviewOptions(api_key="test")
    )
    r["source_sha256"] = "new version"
    ai.apply_ai_review(r)
    assert len(r["review"]["actionable"]) == 1


def test_budget_leaves_unreviewed_candidates_visible(material):
    r = sample()
    second = {**r["review"]["actionable"][0], "message": "Second concern"}
    r["review"]["actionable"].append(second)
    data, originals, gaps = ai.prepare_review(
        r, Path("/repo"), ai.AIReviewOptions(max_candidates=1)
    )
    assert len(data["candidates"]) == len(originals) == 1
    assert any("not reviewed" in g for g in gaps)
    assert len(r["review"]["actionable"]) == 2


@pytest.mark.parametrize("entry", [main, readiness.main])
def test_optional_cli_review_is_forwarded(tmp_path, monkeypatch, capsys, entry):
    def check(root, **kwargs):
        assert kwargs["ai_review"].model == "test-reviewer"
        assert kwargs["ai_review"].max_candidates == 5
        return {"status": "needs_review"}

    monkeypatch.setattr(readiness, "publication_readiness", check)
    args = [
        str(tmp_path),
        "--readiness-ai-review",
        "--readiness-review-model",
        "test-reviewer",
        "--readiness-review-max-candidates",
        "5",
    ]
    if entry is main:
        args.append("--readiness")
    assert entry(args) == 2


def test_opt_in_required_and_bad_limits_rejected():
    for args in [
        [".", "--readiness-ai-review"],
        [
            "--readiness",
            "--readiness-ai-review",
            "--readiness-review-max-candidates",
            "0",
        ],
    ]:
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
