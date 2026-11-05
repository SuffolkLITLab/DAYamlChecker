import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import requests

from dayamlchecker import readiness_research as research
from dayamlchecker.readiness import publication_readiness
from dayamlchecker.yaml_structure import main

URL = "https://court.example/filing"
QUOTE = "File your answer within 30 days."


@pytest.fixture
def package(tmp_path):
    path = tmp_path / "docassemble/demo/data/questions/main.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "metadata:\n  title: Answer\n  jurisdiction: US-MA\n  help_page_url: https://court.example/resources\n---\nid: steps\nquestion: Next steps\nsubquestion: File your answer within 30 days.\n"
    )
    return tmp_path


def response_payload(result=None):
    result = result or {
        "summary": "Deadline may be wrong.",
        "findings": [
            {
                "document_id": "document-0",
                "local_quote": QUOTE,
                "concern": "Check the deadline.",
                "source_urls": [URL],
                "source_explanation": "The court gives a different deadline.",
                "confidence": "high",
            }
        ],
        "document_reviews": [
            {
                "document_id": "document-0",
                "status": "reviewed",
                "source_urls": [URL],
                "explanation": "Compared the filing instructions.",
            }
        ],
        "unresolved_questions": [],
    }
    return {
        "status": "completed",
        "output": [
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "type": "search",
                    "queries": ["Massachusetts answer filing"],
                    "sources": [{"url": URL}],
                },
            },
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {"type": "open_page", "url": URL},
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(result),
                        "annotations": [],
                    }
                ],
            },
        ],
    }


def install_response(monkeypatch, payload, status=200):
    class Response:
        ok = status == 200
        status_code = status

        def json(self):
            return payload

    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(research.requests, "post", post)
    return calls


def test_plain_readiness_never_calls_network(package, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Network called without opt-in")

    monkeypatch.setattr(research.requests, "post", forbidden)
    assert publication_readiness(package)["research"] is None


def test_research_uses_search_open_pages_and_grounded_evidence(package, monkeypatch):
    calls = install_response(monkeypatch, response_payload())
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert report["status"] == "needs_review"
    assert report["execution_status"] == "completed"
    assert report["findings"][0]["repair_context"]["evidence"] == QUOTE
    assert report["findings"][0]["line_number"] == 8
    assert len(report["web_actions"]) == 2
    assert report["sources"][0]["url"] == URL
    request = calls[0][1]["json"]
    assert request["model"] == "gpt-6.1-terra"
    assert request["tools"][0]["type"] == "web_search"
    assert request["max_tool_calls"] == 12
    assert request["text"]["format"] == research.response_format(False)
    assert request["max_output_tokens"] == 12000
    assert len(calls) == 1
    assert "supplemental web searches" in request["instructions"]
    assert "child articles" in request["instructions"]
    assert request["store"] is False
    assert "secret" not in json.dumps(report)


@pytest.mark.parametrize(
    "change",
    [
        {"local_quote": "invented text that is not in the source"},
        {"source_urls": ["https://invented.example/rule"]},
        {"document_id": "missing"},
        {"confidence": "medium"},
    ],
)
def test_ungrounded_findings_become_gaps(package, monkeypatch, change):
    payload = response_payload()
    data = json.loads(payload["output"][-1]["content"][0]["text"])
    data["findings"][0].update(change)
    payload["output"][-1]["content"][0]["text"] = json.dumps(data)
    install_response(monkeypatch, payload)
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert not report["findings"]
    assert report["execution_status"] == "incomplete"
    assert report["status"] == "needs_review"


def test_wrong_quote_key_keeps_rejected_proposal_for_review(package, monkeypatch):
    payload = response_payload()
    data = json.loads(payload["output"][-1]["content"][0]["text"])
    finding = data["findings"][0]
    finding["exact_local_quote"] = finding.pop("local_quote")
    payload["output"][-1]["content"][0]["text"] = json.dumps(data)
    install_response(monkeypatch, payload)
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert not report["findings"]
    assert report["execution_status"] == "incomplete"
    rejected = report["rejected_proposals"][0]
    assert rejected["concern"] == "Check the deadline."
    assert "exact_local_quote" in rejected["received_fields"]
    assert rejected["evidence_status"] == "rejected_do_not_use_as_verified_finding"


def test_no_web_activity_cannot_be_clean_research(package, monkeypatch):
    payload = response_payload(
        {
            "summary": "Fine",
            "findings": [],
            "document_reviews": [],
            "unresolved_questions": [],
        }
    )
    payload["output"] = payload["output"][-1:]
    install_response(monkeypatch, payload)
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert report["status"] == "needs_review"
    assert report["execution_status"] == "incomplete"


@pytest.mark.parametrize("status", [400, 404, 429, 500])
def test_provider_failure_has_no_silent_fallback(package, monkeypatch, status):
    calls = install_response(monkeypatch, {}, status=status)
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert report["execution_status"] == "failed"
    assert str(status) in report["error"]
    assert len(calls) == 1
    assert report["status"] == "needs_review"


def test_timeout_is_unverified_not_pass(package, monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("sensitive request details")

    monkeypatch.setattr(research.requests, "post", timeout)
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert report["execution_status"] == "failed"
    assert "sensitive" not in json.dumps(report)


def test_missing_article_does_not_prevent_supplemental_research(package, monkeypatch):
    path = next(package.rglob("main.yml"))
    path.write_text(
        path.read_text().replace(
            "  help_page_url: https://court.example/resources\n", ""
        )
    )
    calls = install_response(monkeypatch, response_payload())
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert not report["starting_sources"]
    assert calls


def test_template_extraction_and_missing_text_are_visible(package):
    templates = package / "docassemble/demo/data/templates"
    templates.mkdir()
    (templates / "next_steps.txt").write_text("Mail copies to the other party.")
    (templates / "bad.pdf").write_bytes(b"invalid")
    material = research.collect_material(package, research.ResearchOptions())
    assert any("Mail copies" in d["text"] for d in material["documents"])
    assert any("bad.pdf" in gap for gap in material["coverage_gaps"])
    assert any(s["origin"] == "metadata" for s in material["starting_sources"])


def test_input_truncation_never_silently_disappears(package, monkeypatch):
    monkeypatch.setattr(research, "MAX_DOCUMENT_CHARS", 10)
    material = research.collect_material(package, research.ResearchOptions())
    assert material["documents"][0]["truncated"]
    assert any("truncated" in gap for gap in material["coverage_gaps"])


def test_readiness_cli_research_requires_readiness():
    with pytest.raises(SystemExit) as exc:
        main(["--readiness-research", "."])
    assert exc.value.code == 2


def test_research_cli_defaults_and_status(package, monkeypatch, capsys):
    install_response(monkeypatch, response_payload())
    assert (
        main(
            [
                "--readiness",
                str(package),
                "--readiness-research",
                "--openai-api-key",
                "secret",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert report["research"]["model"] == "gpt-6.1-terra"
    assert any(
        c["id"] == "legal_review" and c["status"] == "needs_review"
        for c in report["checks"]
    )
    assert any(
        c["id"] == "instructions_research" and c["status"] == "needs_review"
        for c in report["checks"]
    )


def uncited_report():
    return {
        "summary": "No concrete inconsistency found.",
        "findings": [],
        "document_reviews": [
            {
                "document_id": "document-0",
                "status": "partial",
                "source_urls": [],
                "explanation": "Not every claim could be corroborated.",
            }
        ],
        "unresolved_questions": ["Find support for the stated deadline."],
        "unverified_claims": [
            {
                "document_id": "document-0",
                "local_quote": QUOTE,
                "reason": "No corroborating deadline located.",
                "research_question": "What deadline appears on the applicable court citation?",
            }
        ],
    }


def test_default_research_does_not_require_citations_for_every_claim(
    package, monkeypatch
):
    install_response(monkeypatch, response_payload(uncited_report()))
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret")
    )
    assert report["status"] == "pass"
    assert report["findings"] == []
    assert report["unverified_claims"] == []
    assert report["research_notes"]  # transparent notes, not citation requirements


def test_strict_unverified_inventory_is_opt_in_and_informational(package, monkeypatch):
    calls = install_response(monkeypatch, response_payload(uncited_report()))
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret", strict_unverified=True)
    )
    assert report["status"] == "needs_review"
    assert report["execution_status"] == "completed"
    assert report["findings"] == []
    assert report["unverified_claims"][0]["severity"] == "info"
    assert report["unverified_claims"][0]["local_quote"] == QUOTE
    assert report["unverified_claims"][0]["research_question"]
    assert (
        "Strict unverified-claim inventory is enabled"
        in calls[0][1]["json"]["instructions"]
    )


def test_strict_mode_cannot_succeed_if_provider_omits_inventory(package, monkeypatch):
    data = uncited_report()
    del data["unverified_claims"]
    install_response(monkeypatch, response_payload(data))
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret", strict_unverified=True)
    )
    assert report["execution_status"] == "incomplete"
    assert any("inventory was not returned" in gap for gap in report["coverage_gaps"])


def test_strict_inventory_rejects_invented_local_quote(package, monkeypatch):
    data = uncited_report()
    data["unverified_claims"][0]["local_quote"] = "This is not in the document."
    install_response(monkeypatch, response_payload(data))
    report = research.research_readiness(
        package, research.ResearchOptions(api_key="secret", strict_unverified=True)
    )
    assert not report["unverified_claims"]
    assert report["execution_status"] == "incomplete"


def test_strict_flag_requires_research():
    with pytest.raises(SystemExit) as exc:
        main(["--readiness", "--research-strict-unverified"])
    assert exc.value.code == 2


@pytest.mark.parametrize("strict", [False, True])
def test_research_schema_requires_evidence_fields(strict):
    fmt = research.response_format(strict)
    assert fmt["strict"] is True
    props = fmt["schema"]["properties"]
    assert ("unverified_claims" in props) == strict
    finding = props["findings"]["items"]
    assert "local_quote" in finding["required"]
    assert "failure_example" in finding["required"]

    def check_objects(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                check_objects(child)
        if node.get("type") == "array":
            check_objects(node["items"])

    check_objects(fmt["schema"])
