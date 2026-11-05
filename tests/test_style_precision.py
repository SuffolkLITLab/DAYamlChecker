import json

import pytest

from dayamlchecker import style
from dayamlchecker.yaml_structure import (
    RuntimeOptions,
    find_errors_from_string,
    parse_interview_documents,
)
from dayamlchecker.readiness import publication_readiness, REVIEWS


def check(source, level="precision"):
    return find_errors_from_string(
        source,
        lint_mode="accessibility",
        runtime_options=RuntimeOptions(
            style_enabled=True, style_review_level=level, spellcheck=None
        ),
    )


def test_name_fields_are_not_vague_or_an_actionable_field_count_problem():
    source = "id: name\nquestion: What is your name?\nfields:\n  - code: users[0].name_fields()\n"
    assert not check(source)
    assert any(
        f.message_id == "style_field_count_uncertain" for f in check(source, "thorough")
    )


def test_contextual_choices_and_continue_are_normal_but_symbol_only_labels_are_not():
    result = check(
        'id: eligible\nquestion: Do you rent?\ncontinue button label: Continue\nfields:\n  - Housing: housing\n    choices: [Yes, No, Other, "???"]\n'
    )
    vague = [
        f
        for f in result
        if f.message_id == "accessibility_non_descriptive_choice_label"
    ]
    assert [f.context["snippet"] for f in vague] == ["???"]
    assert not any(
        f.message_id == "accessibility_ambiguous_button_text" for f in result
    )


def test_precision_omits_unconfirmed_vocabulary_but_keeps_concrete_issues():
    source = "id: start\nquestion: Please commence the interview\nfield: answer\n"
    result = check(source)
    assert [
        f.context["matched_text"] for f in result if "matched_text" in f.context
    ] == []
    finding = next(f for f in check(source, "thorough") if "matched_text" in f.context)
    assert finding.context["repair_context"]["source_yaml"] == source
    assert len(check(source, "thorough")) > len(result)


def test_llm_requires_existing_screen_and_literal_evidence():
    docs, _ = parse_interview_documents(
        "id: name\nquestion: What is your name?\nfields:\n  - code: users[0].name_fields()\n"
    )
    payload = json.loads(style._build_screen_payload(docs))
    assert payload[0]["fields"][0]["generated_by"] == "users[0].name_fields()"
    for screen, quote in [
        ("missing", "What is your name?"),
        ("name", "vague name"),
        ("name", ""),
    ]:
        assert (
            style._build_llm_finding(
                parsed_docs=docs,
                input_file="main.yml",
                rule_id="plain-language-rewrite-opportunities",
                message="Issue",
                problematic_text=quote,
                screen_id=screen,
            )
            is None
        )


def test_readiness_requires_revision_bound_review_evidence(tmp_path):
    path = tmp_path / "docassemble/demo/data/questions/main.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "metadata:\n  title: Demo\n  short title: Demo\n  description: Test\n  authors: [Tester]\n  tags: [test]\n  jurisdiction: US-MA\n  can_I_use_this_form: Eligibility\n  before_you_start: Preparation\n---\nid: start\nquestion: Your name\nfields:\n  - Name: user_name\n"
    )
    initial = publication_readiness(tmp_path)
    assert initial["status"] == "needs_review"
    evidence = {
        "source_sha256": initial["source_sha256"],
        **{
            key: {
                "passed": True,
                "reviewer": "Tester",
                "date": "2026-11-05",
                "evidence": "Review record",
            }
            for key in REVIEWS
        },
    }
    assert publication_readiness(tmp_path, evidence=evidence)["status"] == "pass"
    path.write_text(path.read_text() + "\n# changed\n")
    assert (
        publication_readiness(tmp_path, evidence=evidence)["status"] == "needs_review"
    )
    assert publication_readiness(tmp_path / "missing")["status"] == "blocked"


def test_llm_batches_include_screens_after_nonvisible_preamble(monkeypatch):
    source = "---\n".join(
        ["code: x = 1\n"] * 45
        + [
            f"id: screen-{i}\nquestion: Question {i}\nfield: answer_{i}\n"
            for i in range(43)
        ]
    )
    docs, _ = parse_interview_documents(source)
    seen = []

    def provider(**kwargs):
        screens = json.loads(kwargs["user_prompt"].split("Screens JSON:\n")[1])
        seen.append([screen["screen_id"] for screen in screens])
        return {"findings": []}, None

    monkeypatch.setattr(style, "_call_openai_chat_completion", provider)
    style._run_llm_rules(
        parsed_docs=docs,
        input_file="main.yml",
        options=style.StyleLintOptions(include_llm=True),
    )
    assert set(sum(seen, [])) == {f"screen-{i}" for i in range(43)}
    assert max(map(len, seen)) <= 20


def test_precision_keeps_confirmed_vocabulary(monkeypatch):
    def provider(**kwargs):
        if kwargs["user_prompt"].startswith("Triage every vocabulary candidate"):
            candidates = json.loads(kwargs["user_prompt"].split("\n", 1)[1])
            return {
                "decisions": [
                    {
                        "candidate_id": c["candidate_id"],
                        "decision": "keep",
                        "confidence": "high",
                        "reason": "The instruction is ambiguous here.",
                        "evidence": c["text"],
                        "replacement": "Choose",
                        "original_sentence": c["text"],
                        "revised_sentence": c["text"].replace("Select", "Choose"),
                    }
                    for c in candidates
                ]
            }, None
        return {"findings": []}, None

    monkeypatch.setattr(style, "_call_openai_chat_completion", provider)
    result = find_errors_from_string(
        "id: court\nquestion: Select a court\nfield: court\n",
        runtime_options=RuntimeOptions(
            style_include_llm=True, style_openai_api_key="test"
        ),
    )
    assert any(f.context.get("vocabulary_triage_status") == "confirmed" for f in result)


def test_accessibility_findings_include_repair_context():
    result = check('id: detail\nquestion: Details\nfields:\n  - "???": detail\n')
    finding = next(
        f for f in result if f.message_id == "accessibility_non_descriptive_field_label"
    )
    assert finding.context["repair_context"]["screen_id"] == "detail"
    assert '"???": detail' in finding.context["repair_context"]["source_yaml"]


def test_custom_ambiguous_continue_label_still_needs_review():
    findings = check(
        "id: start\nquestion: Details\nfield: answer\ncontinue button label: Here\n"
    )
    assert any(f.message_id == "accessibility_ambiguous_button_text" for f in findings)
