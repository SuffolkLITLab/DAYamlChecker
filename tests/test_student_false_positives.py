"""Counterexamples from student review, paired with defects that must remain visible."""

from dayamlchecker.yaml_structure import RuntimeOptions, find_errors_from_string


def findings(source, code):
    return [
        f
        for f in find_errors_from_string(
            source, runtime_options=RuntimeOptions(style_enabled=True)
        )
        if f.code == code
    ]


def test_numeric_values_are_invariant_but_words_still_need_values():
    source = 'question: How many parents?\nfields:\n  - Count: count\n    choices:\n      - "1"\n      - "2"\n'
    assert not findings(source, "WT701")
    assert findings(source.replace('"2"', "Two"), "WT701")


def test_when_where_heading_has_separate_inputs_but_single_answer_does_not():
    title = "question: When and where was this document notarized?\n"
    assert not findings(
        title + "fields:\n  - State: state\n  - Date: date\n    datatype: date\n",
        "IS715",
    )
    assert findings(title + "field: answer\n", "IS715")
    assert findings(
        title + "fields:\n  - When and where: answer\n  - Your name: name\n", "IS715"
    )


def test_explicit_exit_names_and_text_are_recognized_without_hiding_missing_exit():
    base = "metadata:\n  can_I_use_this_form: Only eligible people\n---\ninclude:\n  - missing.yml\n---\n"
    assert findings(base, "IS743")
    for event, title in [
        ("not_eligible", "Check your answers"),
        ("ineligible_to_complete_screen", "Cannot continue"),
        ("under_18_blocker", "You must be 18 or older"),
        ("under_18_offramp", "You cannot use this form."),
        (
            "restart_interview",
            "Stop, you do not have the required information to continue",
        ),
    ]:
        assert not findings(
            base + f"event: {event}\nquestion: {title}\nbuttons:\n  - Exit: exit\n",
            "IS743",
        )
    assert findings(
        base + "question: You are eligible\nfield: continue_interview\n", "IS743"
    )
    assert findings(
        base
        + "question: Read about households with an ineligible member\nfield: continue_interview\n",
        "IS743",
    )


def test_revisit_table_path_only_removes_the_choices_it_actually_edits():
    source = """question: School and signing
fields:
  - School district: children[i].school_district
    choices:
      - First: first
      - Second: second
  - Signing: signing_choice
    choices:
      - Paper: paper
      - Online: online
---
question: Review your answers
review:
  - Edit: children.revisit
    button: Children
---
continue button field: children.revisit
question: Edit children
subquestion: ${ children.table }
---
table: children.table
rows: children
columns:
  - District: row_item.school_district
edit:
  - school_district
"""
    result = findings(source, "IS724")
    assert result
    assert "signing_choice" in result[0].message
    assert "school_district" not in result[0].message
    readonly = findings(
        source.replace("edit:\n  - school_district", "edit: False"), "IS724"
    )
    assert any("school_district" in f.message for f in readonly)
    unrelated = findings(
        source.replace("  - school_district\n", "  - name.first\n"), "IS724"
    )
    assert any("school_district" in f.message for f in unrelated)
    # A cycle in review destinations must terminate, not imply every answer is editable.
    cycle = source.replace(
        "subquestion: ${ children.table }",
        "review:\n  - Edit: children.revisit\n    button: Children",
    )
    assert findings(cycle, "IS724")


def test_partial_direct_review_does_not_gain_new_warnings():
    source = """question: Select choices
fields:
  - First: first_choice
    choices:
      - Yes: yes
      - No: no
  - Second: second_choice
    choices:
      - Yes: yes
      - No: no
---
question: Review your answers
review:
  - Edit: first_choice
    button: First choice
"""
    assert not findings(source, "IS724")
