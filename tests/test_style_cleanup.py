"""Regression checks for reforms supported by the interview corpus audit."""

from pathlib import Path

import pytest

from dayamlchecker.messages import FindingClass, MessageId
from dayamlchecker.yaml_structure import RuntimeOptions, find_errors_from_string, main


def codes(source: str, *, path: Path | None = None, theme: bool = False) -> set[str]:
    return {
        finding.code
        for finding in find_errors_from_string(
            source,
            input_file=str(path) if path else "<string input>",
            runtime_options=RuntimeOptions(style_enabled=True),
        )
    }


@pytest.mark.parametrize(
    "text",
    [
        "You'll finish soon.",
        "It's easy.",
        "What's next?",
        "We're ready.",
        "I'm ready.",
        "You're ready.",
        "I'll help.",
        "We've finished.",
    ],
)
def test_simple_positive_contractions_are_allowed(text):
    assert "WT705" not in codes(f"question: {text}\nfield: answer\n")


@pytest.mark.parametrize(
    "text,replacement",
    [
        ("can't", "cannot"),
        ("won't", "will not"),
        ("don't", "do not"),
        ("shouldn't", "should not"),
        ("isn’t", "is not"),
        ("could've", "could have"),
        ("should’ve", "should have"),
        ("would’ve", "would have"),
        ("they've", "they have"),
        ("couldn't've", "could not have"),
    ],
)
def test_negative_and_complex_contractions_are_translatability_warnings(
    text, replacement
):
    findings = find_errors_from_string(
        f"question: You'll learn what {text} means.\nfield: answer\n",
        runtime_options=RuntimeOptions(style_enabled=True),
    )
    finding = next(f for f in findings if f.code == "WT705")
    assert finding.finding_class == FindingClass.TRANSLATABILITY
    assert finding.context["matched_text"] == text
    assert finding.context["replacement"] == replacement
    assert "non-native readers or translation tools" in finding.message


def test_negative_contraction_choice_and_legacy_suppression():
    source = "question: Choose\nfields:\n  - Answer: answer\n    choices:\n      - I don't know: unknown\n"
    assert "WT705" in codes(source)
    assert "WT705" not in codes("# no-dayc-block: WS727\n" + source)
    assert "WT705" not in codes("# no-dayc-block: translatability\n" + source)
    assert "WT705" in codes("# no-dayc-block: style\n" + source)


def test_unsafe_plain_language_mappings_are_removed():
    text = "Review the tenant application and find it. It is added because of this condition."
    assert "IS712" not in codes(f"question: {text}\nfield: answer\n")
    assert "IS712" in codes(
        "question: Commence the interview pursuant to this order.\nfield: answer\n"
    )


@pytest.mark.parametrize(
    "question", ["${ heading }", "![Organization logo](logo.png)", "A real heading"]
)
def test_dynamic_logo_and_capitalized_titles_are_present(question):
    assert "WS710" not in codes(f"Question: {question}\nfields:\n  - Name: name\n")
    assert "WS710" in codes("question: ''\nfields:\n  - Name: name\n")


@pytest.mark.parametrize("datatype", ["object", "object_radio", "object_checkboxes"])
def test_object_choices_have_invariant_object_values(datatype):
    assert "WT701" not in codes(
        f"question: Choose\nfields:\n  - Person: person\n    datatype: {datatype}\n    choices:\n      - users[0]\n      - users[1]\n"
    )
    assert "WT701" in codes(
        "question: Choose\nfields:\n  - Answer: answer\n    datatype: checkboxes\n    choices:\n      - I agree\n"
    )


def test_formatting_only_ternaries_are_allowed_but_language_alternatives_warn():
    assert "WT703" not in codes(
        "question: Amount\nsubquestion: ${ currency(amount) if available else '' }\nfield: answer\n"
    )
    assert "WT703" not in codes(
        "question: Date\nsubquestion: ${ format_date(date) if available else '' }\nfield: answer\n"
    )
    assert "WT703" in codes(
        'question: ${ "Your name" if helper else "Their name" }\nfield: answer\n'
    )


def test_capitalized_heading_key_keeps_its_source_line():
    findings = find_errors_from_string(
        "id: long_heading\nmandatory: True\nQuestion: "
        + "Heading " * 20
        + "\nfield: answer\n",
        runtime_options=RuntimeOptions(style_enabled=True),
    )
    finding = next(f for f in findings if f.code == "WS716")
    assert finding.line_number == 3
