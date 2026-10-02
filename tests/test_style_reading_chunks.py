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
