"""Regression checks for reforms supported by the interview corpus audit."""

from pathlib import Path

import pytest

from dayamlchecker.messages import FindingClass, MessageId
from dayamlchecker.style import _longest_prose_span
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


def field_screen(variables: list[str], extra: str = "") -> str:
    return (
        "question: Tell us more\nfields:\n"
        + "".join(f"  - Detail {i}: {name}\n" for i, name in enumerate(variables))
        + extra
    )


@pytest.mark.parametrize("prefix", ["user.address.", "mailing_", "mailing_address_"])
def test_address_components_count_as_one_field(prefix):
    address = [prefix + name for name in ("address", "unit", "city", "state", "zip")]
    assert "WS718" not in codes(
        field_screen(address + [f"answer_{i}" for i in range(5)])
    )
    assert "WS718" in codes(field_screen(address + [f"answer_{i}" for i in range(6)]))


def test_different_addresses_stay_separate():
    variables = [
        prefix + part
        for prefix in ("home.", "work.")
        for part in ("address", "city", "state", "zip")
    ]
    assert "WS718" not in codes(
        field_screen(variables + [f"answer_{i}" for i in range(4)])
    )
    assert "WS718" in codes(field_screen(variables + [f"answer_{i}" for i in range(5)]))


def test_two_address_parts_count_as_one_but_different_roots_do_not():
    others = [f"answer_{i}" for i in range(5)]
    assert "WS718" not in codes(
        field_screen(["mailing_city", "mailing_state"] + others)
    )
    assert "WS718" in codes(field_screen(["mailing_city", "billing_state"] + others))


def test_presentation_items_and_unknown_generated_fields_do_not_inflate_input_count():
    source = field_screen(
        [f"answer_{i}" for i in range(6)],
        "  - note: Read this\n  - html: '<p>Read this</p>'\n  - code: dynamic_fields\n",
    )
    assert "WS718" not in codes(source)


def test_mutually_exclusive_boolean_fields_count_only_visible_inputs():
    source = field_screen([f"answer_{i}" for i in range(5)])
    source += (
        "  - Rent: rent\n    show if: is_renter\n  - Own: own\n    hide if: is_renter\n"
    )
    assert "WS718" not in codes(source)
    assert "WS718" in codes(source + "  - Other: other\n")


def test_address_and_name_parts_are_not_automatically_complex():
    assert "IS720" not in codes(
        field_screen(["first_name", "last_name", "address", "city", "state", "zip"])
    )
    assert "IS720" in codes(field_screen([f"decision_{i}" for i in range(5)]))


def test_inline_help_is_recognized_but_labeled_help_tab_is_discouraged():
    source = field_screen([f"decision_{i}" for i in range(5)])
    assert "IS720" not in codes(
        source + "subquestion: ${ collapse_template(explanation) }\n"
    )
    assert {"IS720", "WS726"}.issubset(
        codes(source + "help:\n  label: Learn more\n  content: An explanation\n")
    )
    assert "WS726" in codes(source + "help: An explanation\n")


def test_field_label_measures_visible_conditional_alternatives_and_links():
    source = "question: Choose\nfields:\n  - label: |\n      % if person_answering == 'helper':\n      What is the tenant's name?\n      % elif person_answering == 'attorney':\n      What is your client's name?\n      % else:\n      What is your name?\n      % endif\n    field: answer\n"
    assert "WS717" not in codes(source)
    assert "WS717" not in codes(
        f"question: Choose\nfields:\n  - label: '[Court website](https://example.com/{'x' * 150})'\n    field: answer\n"
    )
    assert "WS717" in codes(
        f"question: Choose\nfields:\n  - label: {'Long ' * 20}\n    field: answer\n"
    )


def test_long_sentence_in_shorter_branch_is_retained():
    source = (
        "% if option:\n"
        + "Short sentence. " * 15
        + "\n% else:\n"
        + "word " * 24
        + ".\n% endif\n"
    )
    count, snippet = _longest_prose_span(source, sentences=True)
    assert count == 24
    assert snippet.count("word") == 24


def test_sequential_and_nested_conditional_prose_spans():
    source = (
        "word " * 5
        + "\n% if option:\n% if another:\n"
        + "word " * 10
        + "\n% else:\nword\n% endif\n% else:\nword\n% endif\n% if third:\n"
        + "word " * 10
        + "\n% endif\n."
    )
    assert _longest_prose_span(source, sentences=True)[0] == 25
    assert _longest_prose_span(source, sentences=False)[0] == 25


def test_paragraphs_and_lists_do_not_concatenate_into_sentences_or_walls():
    short = "word " * 15
    source = f"question: Read\nsubquestion: |\n  {short}\n\n  {short}.\n\n" + "".join(
        f"  {i}. {short}\n" for i in range(1, 12)
    )
    assert {"WS714", "WS719"}.isdisjoint(codes(source))


def test_soft_wrapped_and_genuinely_long_paragraphs_still_warn():
    source = (
        "question: Read\nsubquestion: |\n  "
        + "word " * 12
        + "\n  "
        + "word " * 12
        + ".\n"
    )
    assert "WS714" in codes(source)
    source = (
        "question: Read\nsubquestion: |\n  "
        + "word " * 125
        + ".\n\n  - A short list item.\n"
    )
    assert "WS719" in codes(source)


def test_html_lists_and_table_rows_form_prose_boundaries():
    items = "".join("<li>" + "word " * 15 + "</li>" for _ in range(12))
    assert "WS719" not in codes(
        "question: Read\nsubquestion: '<ul>" + items + "</ul>'\n"
    )
    assert (
        _longest_prose_span("<p>" + "word " * 125 + "</p>", sentences=False)[0] == 125
    )


def test_conditional_control_and_table_boundaries_are_not_sentence_fragments():
    source = "question: Read\nsubquestion: |\n  % if first:\n  This is complete.\n  % endif\n  % if second:\n  This is also complete.\n  % endif\n"
    assert "WT704" not in codes(source)
    assert "WT704" not in codes(
        "question: Read\nsubquestion: |\n  |Name|Value|\n  % if second:\n  |Joe|One|\n  % endif\n"
    )
    assert "WT704" in codes(
        "question: |\n  What is\n  % if helper:\n  the tenant's\n  % else:\n  your\n  % endif\n  name?\nfield: answer\n"
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


def test_single_role_selection_and_explanatory_sentences_are_not_compound_questions():
    assert "IS715" not in codes(
        "question: Are you an attorney or are you filling this out yourself?\nfield: answer\n"
    )
    assert "IS715" not in codes(
        "question: Do you need help?\nsubquestion: Explain when and how you need help.\nfield: answer\n"
    )
    assert "IS715" in codes(
        "question: Do you rent and do you have a lease?\nfield: answer\n"
    )
    assert "IS715" not in codes(
        "question: Do you and ${ partner } have the same address?\nfield: answer\n"
    )
    assert "IS715" not in codes(
        "question: Do you understand that this lasts 90 days and can be extended?\nfield: answer\n"
    )


def test_paired_acronyms_are_allowed_but_and_or_stays_flagged():
    assert "WS728" not in codes("question: Do you work with DOR/CSE?\nfield: answer\n")
    assert "WS728" in codes("question: Do you rent and/or own?\nfield: answer\n")
    assert "WS728" in codes("question: Do you rent AND/OR own?\nfield: answer\n")
