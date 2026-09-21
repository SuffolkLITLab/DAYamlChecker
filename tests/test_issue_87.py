"""Regression coverage for issue #87's conditional-field reports."""

import textwrap

import pytest

from dayamlchecker.yaml_structure import find_errors_from_string


@pytest.mark.parametrize("field", ["bar", "person.bar", "people[i].bar", "data['bar']"])
@pytest.mark.parametrize(
    "code, expected",
    [
        ("foo\n# {field}", False),
        ('print("{field}")', False),
        ('print("""literal\n{field}\ntext""")', False),
        ("{field} = 1", False),
        ("{field}", True),
        ("print({field})", True),
        ("{field} += 1", True),
        ('print(f"{{{field}}}")', True),
        ("if foo:\n    {field}", False),
        ("# {field}\nif foo:\n    {field}\n{field}", True),
    ],
)
def test_python_references(field, code, expected):
    source = (
        "question: Example\nfields:\n"
        f"  - Value: {field}\n    show if: foo\n"
        "---\nmandatory: True\ncode: |\n"
        + textwrap.indent(code.format(field=field), "  ")
        + "\n"
    )
    findings = find_errors_from_string(source)
    assert any(f.code == "EG308" for f in findings) is expected


@pytest.mark.parametrize("code", ["person.bar", "bar_extra", "other.person.bar"])
def test_unrelated_python_reference(code):
    source = (
        "question: Example\nfields:\n  - Value: bar\n    show if: foo\n"
        "---\nmandatory: True\ncode: |\n  " + code + "\n"
    )
    assert not any(f.code == "EG308" for f in find_errors_from_string(source))


@pytest.mark.parametrize("condition", ["if: foo", "hide if: not foo", ""])
@pytest.mark.parametrize("key", ["attachment", "attachments"])
def test_unsupported_attachment_conditions_do_not_suppress_warning(condition, key):
    # docassemble's process_attachment() does not consume these keys. They do
    # not guarantee that the field is defined when the content is evaluated.
    source = (
        "question: Example\nfields:\n  - Value: bar\n    show if: foo\n"
        f"---\n{key}:\n  - name: Example\n    filename: example\n"
        f"    {condition}\n    content: |\n      ${{ bar }}\n"
    )
    assert any(f.code == "EG416" for f in find_errors_from_string(source))


def test_python_reference_line_ignores_earlier_comment():
    source = (
        "question: Example\nfields:\n  - Value: bar\n    show if: foo\n"
        "---\nmandatory: True\ncode: |\n  # bar\n  bar\n"
    )
    finding = next(f for f in find_errors_from_string(source) if f.code == "EG308")
    assert finding.line_number == 9


@pytest.mark.parametrize(
    "code",
    [
        'print(data["bar"])',
        "print(data [ 'bar' ])",
        "print(data[\n    'bar'\n])",
    ],
)
def test_subscript_reference_normalizes_quotes_and_whitespace(code):
    source = (
        "question: Example\nfields:\n  - Value: data['bar']\n    show if: foo\n"
        "---\nmandatory: True\ncode: |\n" + textwrap.indent(code, "  ") + "\n"
    )
    assert any(f.code == "EG308" for f in find_errors_from_string(source))


def test_invalid_python_still_reports_syntax_error():
    source = (
        "question: Example\nfields:\n  - Value: bar\n    show if: foo\n"
        "---\nmandatory: True\ncode: |\n  if:\n    bar\n"
    )
    findings = find_errors_from_string(source)
    assert any("syntax" in f.message.lower() for f in findings)
    assert not any(f.code == "EG308" for f in findings)
