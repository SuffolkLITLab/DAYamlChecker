"""Check both guide counterexamples and legitimate, less restrictive interfaces."""

from dayamlchecker.style import _variable_name_matches
from dayamlchecker.yaml_structure import RuntimeOptions, find_errors_from_string


def codes(source, *, path=None, theme=False):
    return {
        finding.code
        for finding in find_errors_from_string(
            source,
            input_file=str(path) if path else "<string input>",
            runtime_options=RuntimeOptions(
                style_enabled=True, style_require_custom_theme=theme
            ),
        )
    }


def field_screen(variables):
    return "question: Details\nfields:\n" + "".join(
        f"  - Detail {i}: {name}\n" for i, name in enumerate(variables)
    )


def conditional_screen(condition: str) -> str:
    return "question: Details\nfields:\n" + "".join(
        f"  - Detail {i}: detail_{i}\n    {condition}\n" for i in range(7)
    )


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


def test_enum_and_indexed_visibility_can_still_overload_screen():
    assert "WS718" in codes(
        conditional_screen(
            "show if:\n      variable: users[i].status\n      is: employed"
        )
    )
    assert "WS718" in codes(
        conditional_screen("show if:\n      code: users[i].status == 'employed'")
    )
    assert "WS718" not in codes(conditional_screen("show if: False"))


def test_unknown_visibility_and_generated_inputs_have_coverage_advisories():
    unknown = codes(conditional_screen("show if:\n      code: custom_check()"))
    assert "IS740" in unknown
    assert "WS718" not in unknown
    assert "IS740" in codes("question: Details\nfields:\n  - code: make_fields()\n")
    assert "IS740" not in codes(
        "question: Details\nfields:\n  - Choice: selected\n    code: make_choices()\n"
    )


def test_mutually_exclusive_enum_groups_do_not_inflate_count():
    source = "question: Details\nfields:\n" + "".join(
        f"  - Detail {kind} {i}: {kind}_{i}\n    show if:\n      variable: category\n      is: {kind}\n"
        for kind in ("first", "second")
        for i in range(6)
    )
    assert {"WS718", "IS740"}.isdisjoint(codes(source))


def test_top_level_help_is_separate_even_with_custom_label():
    assert "WS726" in codes(
        "question: Details\nfield: answer\nhelp:\n  label: Learn more\n  content: Explanation\n"
    )


def test_formatted_prose_still_has_length_limits():
    source = "question: Details\nfield: answer\nsubquestion: |\n"
    paragraphs = source + "  " + "word " * 65 + "\n\n  " + "word " * 65 + "\n"
    assert "IS741" not in codes(paragraphs)
    assert "WS719" not in codes(paragraphs)
    assert "WS719" in codes(source + "  * " + "word " * 125 + "\n")


def test_unknown_includes_are_visible_but_known_positive_evidence_wins(tmp_path):
    source = "metadata:\n  title: Example\n  can_I_use_this_form: Only eligible people\n---\ninclude:\n  - missing-theme.yml\n"
    path = tmp_path / "main.yml"
    assert {"IS743", "IS744"}.issubset(codes(source, path=path, theme=True))
    complete = (
        source
        + "---\nfeatures:\n  css: styles.css\n---\nquestion: You do not qualify\nbuttons:\n  - Exit: exit\n"
    )
    assert {"IS721", "IS722", "IS743", "IS744"}.isdisjoint(
        codes(complete, path=path, theme=True)
    )


def test_address_exception_still_preserves_overload_signal():
    address = [f"user.address.{part}" for part in ("address", "city", "state", "zip")]
    assert "WS718" not in codes(
        field_screen(address + [f"answer_{i}" for i in range(5)])
    )
    assert "WS718" in codes(field_screen(address + [f"answer_{i}" for i in range(6)]))
