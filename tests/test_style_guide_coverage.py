"""Check both guide counterexamples and legitimate, less restrictive interfaces."""

from dayamlchecker.style import _variable_name_matches
from dayamlchecker.yaml_structure import RuntimeOptions, find_errors_from_string


def codes(source, *, path=None, theme=False):
    return {
        finding.code
        for finding in find_errors_from_string(
            source,
            input_file=str(path) if path else "<string input>",
            runtime_options=RuntimeOptions(style_enabled=True),
        )
    }


def test_guide_or_question_and_single_choice_alternative():
    # The readability guide's compound-question example.
    assert "IS715" in codes(
        "question: Do you currently have a case in the Probate and Family Court or are you planning to file one?\nfield: answer\n"
    )
    assert "IS715" not in codes("question: Do you rent or own?\nfield: answer\n")
    assert "IS715" not in codes(
        "question: What method of delivery have you used or will you use?\nfield: answer\n"
    )
    assert "IS715" not in codes(
        "question: When did or will you make service?\nfield: answer\n"
    )
    assert "IS715" not in codes(
        "question: What is the amount?\nsubquestion: How much? And how often?\nfield: answer\n"
    )


def test_formatted_prose_still_has_length_limits():
    source = "question: Details\nfield: answer\nsubquestion: |\n"
    paragraphs = source + "  " + "word " * 65 + "\n\n  " + "word " * 65 + "\n"
    assert "IS741" not in codes(paragraphs)
    assert "WS719" not in codes(paragraphs)
    assert "WS719" in codes(source + "  * " + "word " * 125 + "\n")
