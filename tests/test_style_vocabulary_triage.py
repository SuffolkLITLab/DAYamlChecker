"""High-recall vocabulary candidates and conservative optional model triage."""

import json

import pytest

from dayamlchecker import style
from dayamlchecker.messages import Severity
from dayamlchecker.yaml_structure import RuntimeOptions, find_errors_from_string


def findings(source, llm=False):
    return find_errors_from_string(
        source,
        runtime_options=RuntimeOptions(
            style_enabled=True,
            style_include_llm=llm,
            style_openai_api_key="test-key" if llm else None,
        ),
    )


def vocabulary(result):
    return [f for f in result if f.context.get("vocabulary_triage_candidate")]


def fake_provider(monkeypatch, decide):
    batches = []

    def call(**kwargs):
        if kwargs["user_prompt"].startswith("Triage every vocabulary candidate"):
            batch = json.loads(kwargs["user_prompt"].split("\n", 1)[1])
            batches.append(batch)
            return decide(batch), None
        return {"findings": []}, None

    monkeypatch.setattr(style, "_call_openai_chat_completion", call)
    return batches


def decision(candidate, disposition="dismiss", confidence="high", **extra):
    return {
        "candidate_id": candidate["candidate_id"],
        "decision": disposition,
        "confidence": confidence,
        "reason": "This is a document name, not an instruction verb.",
        "evidence": candidate["text"],
        **extra,
    }


@pytest.mark.parametrize("term", ["please", "select", "option"])
def test_straightforward_style_preferences_return_without_model(term):
    result = vocabulary(findings(f"question: Please select an option\nfield: answer\n"))
    finding = next(f for f in result if f.context["matched_text"].lower() == term)
    assert finding.code == "IS712"
    assert finding.severity == Severity.INFO
    assert finding.context["vocabulary_triage_status"] == "not_reviewed"


@pytest.mark.parametrize(
    "text,term",
    [
        ("Court Activity Record Request Form", "request"),
        ("Your bug report is public", "report"),
        ("Your SSI benefit may change", "benefit"),
        ("Read the following instructions", "following"),
    ],
)
def test_contextual_candidates_do_not_prescribe_wrong_substitutions(text, term):
    candidate = next(
        f
        for f in vocabulary(findings(f"question: {text}\nfield: answer\n"))
        if f.context["matched_text"].lower() == term
    )
    assert candidate.code == "IS746"
    assert "if the meaning permits" in candidate.message
    assert "consider replacing" not in candidate.message


def test_high_confidence_grounded_dismissal_only_removes_vocabulary(monkeypatch):
    batches = fake_provider(
        monkeypatch, lambda batch: {"decisions": [decision(c) for c in batch]}
    )
    result = findings(
        "question: Commence the Court Activity Record Request Form\nfield: answer\n",
        llm=True,
    )
    assert len(batches) == 1
    assert vocabulary(result) == []
    assert any(f.context.get("matched_text") == "Commence" for f in result)


def test_keep_can_refine_grammatical_alternative_and_records_reason(monkeypatch):
    fake_provider(
        monkeypatch,
        lambda batch: {
            "decisions": [
                decision(
                    c,
                    "keep",
                    replacement="ask for",
                    reason="A verb here can be simpler.",
                )
                for c in batch
            ]
        },
    )
    result = vocabulary(
        findings("question: Will you request a fee waiver?\nfield: answer\n", llm=True)
    )
    assert len(result) == 1
    assert result[0].context["replacement"] == "ask for"
    assert result[0].context["vocabulary_triage_status"] == "confirmed"
    assert (
        result[0].context["vocabulary_triage_reason"] == "A verb here can be simpler."
    )
    assert result[0].severity == Severity.INFO


@pytest.mark.parametrize(
    "disposition,confidence",
    [("uncertain", "high"), ("dismiss", "medium"), ("dismiss", "low")],
)
def test_uncertainty_preserves_recall(monkeypatch, disposition, confidence):
    fake_provider(
        monkeypatch,
        lambda batch: {
            "decisions": [decision(c, disposition, confidence) for c in batch]
        },
    )
    result = vocabulary(
        findings("question: Read your financial report\nfield: answer\n", llm=True)
    )
    assert len(result) == 1
    assert result[0].context["vocabulary_triage_status"] == "uncertain"


@pytest.mark.parametrize(
    "response",
    [None, "not JSON", {"decisions": []}, {"findings": []}, {"decisions": [None]}],
)
def test_invalid_or_incomplete_response_keeps_candidates(monkeypatch, response):
    fake_provider(monkeypatch, lambda batch: response)
    result = findings("question: Read your financial report\nfield: answer\n", llm=True)
    assert len(vocabulary(result)) == 1
    assert any(f.code == "ES793" for f in result)


@pytest.mark.parametrize(
    "change",
    [
        {"evidence": "an invented financial report quote"},
        {"evidence": "report"},
        {"evidence": "Read your financial"},
        {"candidate_id": "unknown"},
        {"decision": []},
        {"confidence": {}},
        {"reason": ""},
        {"replacement": []},
    ],
)
def test_invalid_decision_cannot_remove_candidate(monkeypatch, change):
    fake_provider(
        monkeypatch, lambda batch: {"decisions": [decision(c, **change) for c in batch]}
    )
    result = findings("question: Read your financial report\nfield: answer\n", llm=True)
    assert len(vocabulary(result)) == 1
    assert any(f.code == "ES793" for f in result)


def test_conflicting_duplicate_or_missing_ids_cannot_remove_batch(monkeypatch):
    for modify in (lambda items: items + items[:1], lambda items: items[:1]):
        fake_provider(
            monkeypatch,
            lambda batch: {"decisions": modify([decision(c) for c in batch])},
        )
        result = findings(
            "question: Please read your financial report\nfield: answer\n", llm=True
        )
        assert len(vocabulary(result)) == 2
        assert any(f.code == "ES793" for f in result)


def test_request_failure_keeps_candidates_and_sanitized_error(monkeypatch):
    monkeypatch.setattr(
        style,
        "_call_openai_chat_completion",
        lambda **kwargs: (None, "network request failed"),
    )
    result = findings("question: Read your financial report\nfield: answer\n", llm=True)
    assert len(vocabulary(result)) == 1
    assert any(
        f.code == "ES793" and f.context.get("rule_id") == "vocabulary-triage"
        for f in result
    )
    assert all("test-key" not in str(f) for f in result)


def test_default_mode_never_calls_a_provider(monkeypatch):
    def unexpected_call(**kwargs):
        pytest.fail("deterministic checks must not call a provider")

    monkeypatch.setattr(style, "_call_openai_chat_completion", unexpected_call)
    assert (
        len(
            vocabulary(
                findings("question: Read your financial report\nfield: answer\n")
            )
        )
        == 1
    )


def test_candidates_do_not_crowd_out_stronger_suggestions():
    suggestions = style._find_plain_language_suggestions(
        "Please select an option, request a report, and benefit from the following. "
        "Commence.",
        max_matches=1,
    )
    terms = {term.lower() for term, _ in suggestions}
    assert terms == {
        "please",
        "select",
        "option",
        "request",
        "report",
        "benefit",
        "following",
        "commence",
    }


def test_longer_ordinary_phrase_takes_precedence_over_candidate():
    terms = {
        term.lower()
        for term, _ in style._find_plain_language_suggestions("Please find enclosed")
    }
    assert "please find enclosed" in terms
    assert "please" not in terms


def test_missing_triage_prompt_preserves_candidates(monkeypatch):
    monkeypatch.setattr(style, "_load_llm_prompt_templates", lambda: {})

    def unexpected_call(**kwargs):
        pytest.fail("must not call the provider without triage instructions")

    monkeypatch.setattr(style, "_call_openai_chat_completion", unexpected_call)
    result = findings("question: Read your financial report\nfield: answer\n", llm=True)
    assert len(vocabulary(result)) == 1
    assert any(f.code == "ES793" for f in result)


def test_candidate_triage_covers_all_screens_with_bounded_batches(monkeypatch):
    batches = fake_provider(
        monkeypatch, lambda batch: {"decisions": [decision(c) for c in batch]}
    )
    source = "---\n".join(
        f"id: screen_{i}\nquestion: Read your financial report\nfield: answer_{i}\n"
        for i in range(45)
    )
    assert vocabulary(findings(source, llm=True)) == []
    assert [len(batch) for batch in batches] == [20, 20, 5]
    assert batches[-1][-1]["screen_id"] == "screen_44"


def test_triage_retains_template_branches_and_late_field_label_context(monkeypatch):
    batches = fake_provider(
        monkeypatch,
        lambda batch: {"decisions": [decision(c, "uncertain") for c in batch]},
    )
    source = "question: Read\nsubquestion: |\n  % if helper:\n  Read the financial report\n  % else:\n  Report problems to the inspector\n  % endif\nfields:\n  - Request a fee waiver: waiver\n"
    result = vocabulary(findings(source, llm=True))
    assert len(result) == 2
    assert "% if helper" in batches[0][0]["text"]
    assert any(
        c["location"].startswith("fields") and "Request a fee waiver" in c["text"]
        for c in batches[0]
    )


def test_truncated_context_cannot_be_dismissed(monkeypatch):
    batches = fake_provider(
        monkeypatch, lambda batch: {"decisions": [decision(c) for c in batch]}
    )
    result = vocabulary(
        findings(
            "question: Read\nsubquestion: "
            + "Read your financial report. "
            + "word " * 1500
            + "\nfield: answer\n",
            llm=True,
        )
    )
    assert len(result) == 1
    assert batches[0][0]["context_truncated"]
    assert result[0].context["vocabulary_triage_status"] == "uncertain"


def test_truncated_question_cannot_authorize_field_label_dismissal(monkeypatch):
    batches = fake_provider(
        monkeypatch, lambda batch: {"decisions": [decision(c) for c in batch]}
    )
    result = vocabulary(
        findings(
            "question: "
            + "word " * 300
            + "\nfields:\n  - Request a fee waiver: waiver\n",
            llm=True,
        )
    )
    assert len(result) == 1
    assert batches[0][0]["context_truncated"]
    assert result[0].context["vocabulary_triage_status"] == "uncertain"
