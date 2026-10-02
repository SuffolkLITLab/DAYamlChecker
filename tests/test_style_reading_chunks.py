"""Readability heuristics credit useful structure while catching dense chunks."""

from pathlib import Path

import pytest

from dayamlchecker.yaml_structure import RuntimeOptions, find_errors_from_string


def codes(source: str, path: Path | None = None) -> set[str]:
    return {
        finding.code
        for finding in find_errors_from_string(
            source,
            input_file=str(path) if path else "<string input>",
            runtime_options=RuntimeOptions(style_enabled=True),
        )
    }


def screen(text: str) -> str:
    return "question: Instructions\nfield: answer\nsubquestion: |\n" + "".join(
        "  " + line + "\n" for line in text.splitlines()
    )


@pytest.mark.parametrize("marker", ["-", "*", "+", "1.", "1)"])
def test_many_short_list_items_do_not_form_a_wall(marker):
    text = "\n".join(marker + " " + "word " * 25 for _ in range(20))
    assert {"WS719", "IS741"}.isdisjoint(codes(screen(text)))


def test_many_short_paragraphs_do_not_trigger_total_length_advice():
    text = "\n\n".join("word " * 40 for _ in range(12))
    assert {"WS719", "IS741"}.isdisjoint(codes(screen(text)))


def test_short_table_cells_are_independent_even_in_a_long_row():
    cells = ["word " * 30 for _ in range(6)]
    markdown = "| " + " | ".join(cells) + " |"
    without_outer_pipes = (
        " | ".join(cells) + "\n" + " | ".join(["---"] * 6) + "\n" + " | ".join(cells)
    )
    html = (
        "<table><tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr></table>"
    )
    for text in (markdown, without_outer_pipes, html):
        assert {"WS719", "IS741"}.isdisjoint(codes(screen(text)))


@pytest.mark.parametrize(
    "text",
    [
        "- " + "word " * 65 + "\n  " + "word " * 65,
        "| Label | " + "word " * 125 + " |",
        "<table><tr><td>" + "word " * 65 + "\n" + "word " * 65 + "</td></tr></table>",
        "## Useful heading\n- A short item\n\n" + "word " * 125,
    ],
)
def test_formatting_does_not_hide_a_dense_reading_chunk(text):
    assert "WS719" in codes(screen(text))


def test_wrapped_list_item_keeps_conditional_alternatives_separate():
    text = (
        "% if helper:\n- "
        + "word " * 65
        + "\n% else:\n- "
        + "word " * 65
        + "\n% endif\n  "
        + "word " * 40
    )
    assert "WS719" not in codes(screen(text))
    assert "WS719" in codes(screen(text.replace("word " * 40, "word " * 65)))


def test_headings_are_not_joined_to_the_following_sentence():
    for heading in ("## " + "word " * 10, "<h2>" + "word " * 10 + "</h2>"):
        assert "WS714" not in codes(screen(heading + "\n" + "word " * 15 + "."))


PREVIEW = "id: review before signature\nquestion: Preview your form\nfield: reviewed\nsubquestion: '[FILE form.pdf]'\n"


def test_preview_warns_only_when_back_is_explicitly_disabled():
    assert "IS742" not in codes(PREVIEW)
    assert "IS742" in codes("prevent going back: True\n" + PREVIEW)
    assert "IS742" not in codes("prevent going back: is_submitted\n" + PREVIEW)
    disabled = "features:\n  navigation back button: False\n---\n"
    assert "IS742" in codes(disabled + PREVIEW)
    assert "IS742" not in codes(disabled + "back button: True\n" + PREVIEW)
    assert "IS742" not in codes(
        disabled.replace("---", "  question back button: True\n---") + PREVIEW
    )


def test_preview_back_configuration_from_local_include(tmp_path):
    (tmp_path / "navigation.yml").write_text(
        "features:\n  navigation back button: False\n"
    )
    source = "include:\n  - navigation.yml\n---\n" + PREVIEW
    path = tmp_path / "interview.yml"
    path.write_text(source)
    assert "IS742" in codes(source, path)


def test_native_answer_review_still_checks_edit_controls_on_preview():
    assert "WS723" in codes(PREVIEW + "review:\n  - label: Summary\n")


def test_custom_table_cell_edit_link_is_a_correction_control():
    source = "question: Review your answers\nfield: reviewed\nsubquestion: ${ users.table }\n---\ntable: users.table\nrows: users\ncolumns:\n  - Name: row_item.name\n  - Edit: |\n      [Edit](${ url_action('user_name') })\n"
    assert {"WS723", "IS745"}.isdisjoint(codes(source))


def test_add_control_only_supports_correction_when_existing_items_can_be_removed():
    source = "question: Review your answers\nfield: reviewed\nsubquestion: ${ users.table } ${ users.add_action() }\n---\ntable: users.table\nrows: users\ncolumns:\n  - Name: row_item.name\n"
    assert "WS723" in codes(source)
    assert "WS723" not in codes(source + "delete buttons: True\n")


def test_table_render_can_explicitly_hide_otherwise_available_edit_controls():
    source = "question: Review your answers\nfield: reviewed\nsubquestion: ${ users.table }\n---\ntable: users.table\nrows: users\ncolumns:\n  - Name: row_item.name\nedit:\n  - name\n"
    assert "WS723" not in codes(source)
    assert "WS723" in codes(
        source.replace("${ users.table }", "${ users.table.show(editable=False) }")
    )
    assert {"WS723", "IS745"}.isdisjoint(codes(source + "read only: protected\n"))
    assert "WS723" not in codes(source.replace("edit:\n  - name", "edit: True"))
    assert {"WS723", "IS745"}.isdisjoint(
        codes(
            source.replace(
                "${ users.table }", "${ users.table.show(editable=can_edit) }"
            )
        )
    )


def test_unresolved_table_only_defers_its_own_choice_coverage():
    source = "question: Type of case\nfields:\n  - Type: case_type\n    choices:\n      - Civil: civil\n      - Criminal: criminal\n---\nquestion: Review your answers\nreview:\n  - Edit: user.name\n    button: Name\nsubquestion: ${ exhibits.table }\n"
    assert "IS724" in codes(source)
    assert "IS724" not in codes(source.replace("case_type", "exhibits.case_type"))
    assert "IS745" not in codes(source)


def test_local_table_definition_and_action_destination_are_resolved(tmp_path):
    (tmp_path / "table.yml").write_text(
        "table: users.table\nrows: users\ncolumns:\n  - Name: row_item.name\n  - Change: |\n      [Edit](${ url_action('edit_choices') })\n---\nevent: edit_choices\nquestion: Correct your case\nfields:\n  - Type: case_type\n"
    )
    source = "include:\n  - table.yml\n---\nquestion: Type of case\nfields:\n  - Type: case_type\n    choices:\n      - Civil: civil\n      - Criminal: criminal\n---\nquestion: Review your answers\nfield: reviewed\nsubquestion: ${ users.table }\n"
    path = tmp_path / "main.yml"
    path.write_text(source)
    assert {"WS723", "IS724", "IS745"}.isdisjoint(codes(source, path))
    table = tmp_path / "table.yml"
    table.write_text(table.read_text().replace("case_type", "another_field"))
    assert "IS724" in codes(source, path)
