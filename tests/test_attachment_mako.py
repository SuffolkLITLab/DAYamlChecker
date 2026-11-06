import json

import pytest

from dayamlchecker.readiness import main as readiness_main
from dayamlchecker.yaml_structure import find_errors_from_string, main

ATTACHMENT = """\
id: document
question: Your document
attachment:
  name: Example
  filename: example
  pdf template file: example.pdf
  variable name: document
  skip undefined: True
  fields:
    - "users1_telephone_number": {expression}
"""
BAD_EXPRESSION = "${ users[0]telepone_number}"
GOOD_EXPRESSION = "${ users[0].telephone_number }"


def mako_findings(source):
    return [
        finding
        for finding in find_errors_from_string(source, input_file="<test>")
        if finding.code in {"EG111", "EG112"}
    ]


def test_syntax_error_reports_location_expression_and_diagnostic():
    source = ATTACHMENT.format(expression=BAD_EXPRESSION)
    (finding,) = mako_findings(source)
    assert finding.code == "EG111"
    assert finding.line_number == 10
    assert finding.context["location"] == (
        "attachment.fields[0].users1_telephone_number"
    )
    assert finding.context["expression"] == BAD_EXPRESSION
    assert "invalid syntax" in finding.context["error"]
    assert "skip undefined" in finding.err_str


def test_syntax_error_line_is_relative_to_the_whole_file():
    source = "metadata:\n  title: T\n---\n" + ATTACHMENT.format(
        expression=BAD_EXPRESSION
    )
    (finding,) = mako_findings(source)
    assert finding.line_number == 13


def test_valid_expression_needs_no_defined_variables():
    assert mako_findings(ATTACHMENT.format(expression=GOOD_EXPRESSION)) == []


@pytest.mark.parametrize(
    "source,location,line_number",
    [
        (
            "attachments:\n  - name: ok\n    filename: ${ a b }\n    content: x\n",
            "attachments[0].filename",
            3,
        ),
        (
            "attachment:\n  - name: ${ a b }\n    content: x\n",
            "attachment[0].name",
            2,
        ),
        (
            "attachment:\n  name: ok\n  docx template file: a.docx\n  fields:\n"
            "    first: ok\n    second: ${ a b }\n",
            "attachment.fields.second",
            6,
        ),
        (
            "attachment:\n  name: ok\n  docx template file: a.docx\n  fields:\n"
            "    outer:\n      - inner:\n          - ${ a b }\n",
            "attachment.fields.outer[0].inner[0]",
            7,
        ),
        (
            "attachment:\n  name: ok\n  content: x\n  metadata:\n"
            "    author:\n      - ${ a b }\n",
            "attachment.metadata.author[0]",
            6,
        ),
        (
            "attachment:\n  name: ok\n  content: |\n    first\n    second ${ a b }\n",
            "attachment.content",
            5,
        ),
        (
            "attachment:\n  name: ok\n  content: x\n  owner password: ${ a b }\n",
            "attachment.owner password",
            4,
        ),
        (
            "ATTACHMENT:\n  Name: ${ a b }\n  content: x\n",
            "ATTACHMENT.Name",
            2,
        ),
    ],
)
def test_attachment_forms_and_nested_structures(source, location, line_number):
    (finding,) = mako_findings("question: Document\n" + source)
    assert finding.context["location"] == location
    assert finding.line_number == line_number + 1


@pytest.mark.parametrize(
    "content",
    [
        "% if user.is_tenant:\n  Tenant\n% elif user.is_owner:\n  Owner\n% endif",
        "% for item in items:\n  ${ item }\n% endfor",
        '${ {"a": {"b": 1}}["a"]["b"] }',
        "${ 'closing } brace' }",
        "<%text>${ not an expression }</%text>",
        "${ '${' } literal",
        "\\${ escaped }",
        "<% total = sum(costs) %>${ total }",
        '<%def name="label()">Label</%def>${ label() }',
        "## A Mako comment\n${ value }",
        "${ value | h }",
    ],
)
def test_valid_multiline_and_literal_mako_passes(content):
    indented = "\n".join("    " + line for line in content.splitlines())
    source = f"question: Document\nattachment:\n  name: ok\n  content: |\n{indented}\n"
    assert mako_findings(source) == []


@pytest.mark.parametrize(
    "content,code,line_number",
    [
        ("first\n% if a:\n${ a[0]b }\n% endif", "EG111", 7),
        ("% if a:\nnever closed", "EG111", 5),
        ("${ unterminated", "EG111", 5),
        ("<%foo>", "EG112", 5),
        ("% for loop in items:\nx\n% endfor", "EG112", 5),
        ("<%! return %>", "EG112", 5),
    ],
)
def test_invalid_multiline_mako_fails(content, code, line_number):
    indented = "\n".join("    " + line for line in content.splitlines())
    source = f"question: Document\nattachment:\n  name: ok\n  content: |\n{indented}\n"
    (finding,) = mako_findings(source)
    assert finding.code == code
    assert finding.line_number == line_number


@pytest.mark.parametrize(
    "line",
    [
        # docassemble does not compile text without a Mako marker.
        'fields:\n    - "percent": "% of income"',
        # These hold Python or file references, not Mako.
        "field code:\n    - amount: ${ a b }",
        "variable name: ${ a b }",
        "pdf template file: ${ a b }.pdf",
        "skip undefined: ${ a b }",
    ],
)
def test_text_docassemble_does_not_compile_as_mako_is_ignored(line):
    source = f"question: Document\nattachment:\n  name: ok\n  {line}\n"
    assert mako_findings(source) == []


def test_compiling_does_not_run_module_level_blocks():
    source = (
        "question: Document\nattachment:\n  name: ok\n  content: |\n"
        '    <%! raise RuntimeError("interview code ran") %>\n'
    )
    assert mako_findings(source) == []


def test_question_mako_errors_are_reported_once():
    source = "question: ${ a b }\nattachment:\n  name: ${ c d }\n  content: x\n"
    findings = mako_findings(source)
    assert len(findings) == 2
    assert sum("attachment.name" in finding.err_str for finding in findings) == 1


def test_cli_reports_attachment_mako_error(tmp_path, capsys):
    path = tmp_path / "interview.yml"
    path.write_text(ATTACHMENT.format(expression=BAD_EXPRESSION))
    assert main([str(path), "--no-url-check"]) == 1
    output = capsys.readouterr().out
    assert f"ERROR [EG111] {path}:10" in output
    assert "attachment.fields[0].users1_telephone_number" in output

    path.write_text(ATTACHMENT.format(expression=GOOD_EXPRESSION))
    assert main([str(path), "--no-url-check"]) == 0
    assert "EG111" not in capsys.readouterr().out


def test_readiness_gates_on_attachment_mako_error(tmp_path, capsys):
    path = tmp_path / "docassemble/demo/data/questions/main.yml"
    path.parent.mkdir(parents=True)
    source = (
        "metadata:\n  title: Example\n  short title: Example\n"
        "  description: A form\n  authors: [Author]\n  tags: [test]\n"
        "  jurisdiction: US-MA\n  can_I_use_this_form: Eligibility\n"
        "  before_you_start: Preparation\n---\n"
    )

    def run_readiness(expression):
        path.write_text(source + ATTACHMENT.format(expression=expression))
        readiness_main([str(tmp_path)])
        return json.loads(capsys.readouterr().out)

    def mako_gates(report):
        return [
            finding
            for finding in report["findings"]
            if finding["message_id"] == "attachment_mako_syntax_error"
            and finding["release_gate"]
        ]

    assert mako_gates(run_readiness(GOOD_EXPRESSION)) == []
    (gate,) = mako_gates(run_readiness(BAD_EXPRESSION))
    assert gate["line_number"] == 20
