from pathlib import Path

import pytest

from dayamlchecker._jinja import render_yaml
from dayamlchecker.fixer import plan_file
from dayamlchecker.messages import MessageId
from dayamlchecker.yaml_structure import find_errors, find_errors_from_string, main

FIXTURES = Path(__file__).parent / "fixtures" / "jinja"


def test_includes_loops_and_normal_validation():
    path = FIXTURES / "interview.yml"
    rendered = render_yaml(path.read_text(), str(path))
    assert "likes_apple" in rendered and "likes_pear" in rendered
    assert "{%" not in rendered
    assert find_errors(str(path)) == find_errors_from_string(
        rendered, input_file=f"{path} (rendered Jinja)"
    )
    assert not any(f.severity == "error" for f in find_errors(str(path)))


def test_included_invalid_python_is_validated(tmp_path):
    (tmp_path / "included.yml").write_text("code: |\n  broken =\n")
    path = tmp_path / "main.yml"
    path.write_text('# use jinja\n{% include "included.yml" %}\n')
    findings = find_errors(str(path))
    finding = next(f for f in findings if f.message_id == MessageId.PYTHON_SYNTAX_ERROR)
    assert finding.file_name == f"{path} (rendered Jinja)"
    assert finding.line_number is not None


@pytest.mark.parametrize(
    "body, expected",
    [
        ("{% if %}", "Expected an expression"),
        ('{% include "absent.yml" %}', "absent.yml"),
        ("question: {{ missing }}", "missing"),
        ("{% if __debug__ %}question: Debug{% endif %}", "__debug__"),
        ("question: {{ 1 / 0 }}", "division by zero"),
        ("{{ ''.__class__.__mro__ }}", "unsafe"),
    ],
)
def test_render_failures_are_findings(tmp_path, body, expected):
    findings = find_errors_from_string(
        "# use jinja\n" + body, input_file=str(tmp_path / "main.yml")
    )
    assert len(findings) == 1
    assert findings[0].message_id == MessageId.JINJA_RENDER_ERROR
    assert expected in findings[0].message


def test_syntax_error_in_include_has_source_location(tmp_path):
    included = tmp_path / "bad.yml"
    included.write_text("question: Hello\n{% if %}\n")
    findings = find_errors_from_string(
        '# use jinja\n{% include "bad.yml" %}',
        input_file=str(tmp_path / "main.yml"),
    )
    assert findings[0].file_name == str(included)
    assert findings[0].line_number == 2


def test_jinja_is_opt_in_and_preserves_mako():
    source = "question: |\n  {{ literal }} and ${ answer }\n"
    assert render_yaml("# use jinja\n{% raw %}" + source + "{% endraw %}") == (
        "# use jinja\n" + source
    )
    assert not any(
        f.message_id == MessageId.JINJA_RENDER_ERROR
        for f in find_errors_from_string(source)
    )


def test_string_input_and_crlf():
    findings = find_errors_from_string(
        '# use jinja\r\n{% set value = "broken =" %}\r\ncode: |\r\n  {{ value }}\r\n'
    )
    assert any(f.message_id == MessageId.PYTHON_SYNTAX_ERROR for f in findings)


def test_cli_reports_generated_errors_and_honors_rendered_suppressions(
    tmp_path, capsys
):
    path = tmp_path / "main.yml"
    path.write_text('# use jinja\n{{ "\\n" * 10 }}\n---\ncode: |\n  broken =\n')
    assert main([str(path), "--no-docx-accessibility"]) == 1
    assert "rendered Jinja" in capsys.readouterr().out
    path.write_text(
        '# use jinja\n{{ "\\n" * 10 }}\n---\n'
        "# no-dayc-block: EG122\ncode: |\n  broken =\n# end of block\n"
    )
    assert main([str(path), "--no-docx-accessibility"]) == 0


def test_fixer_leaves_even_yaml_parseable_templates_untouched(tmp_path):
    path = tmp_path / "main.yml"
    source = '# use jinja\nquestion: "{{ 1 + 1 }}"\nyesno: answer\n'
    path.write_text(source)
    plan = plan_file(path)
    assert plan.skipped_reason == "Jinja templates cannot be automatically rewritten"
    assert path.read_text() == source


def test_conditionals_and_generated_yaml_errors():
    source = (
        "# use jinja\n{% set enabled = true %}\n"
        "{% if enabled %}question: [unclosed{% else %}question: Fine{% endif %}\n"
    )
    assert any(
        f.message_id == MessageId.YAML_PARSE_ERROR
        for f in find_errors_from_string(source)
    )
    assert not any(
        f.severity == "error"
        for f in find_errors_from_string(
            source.replace("enabled = true", "enabled = false")
        )
    )


def test_docassemble_documented_include_pattern(tmp_path):
    # Adapted from docassemble's examples/jinjayaml{,-included}.yml.
    (tmp_path / "fruit.yml").write_text(
        "id: fruit\nquestion: |\n  What is your favorite fruit?\n"
        "fields:\n  - Fruit: favorite_fruit\n---\n"
    )
    source = (
        '# use jinja\n{% include "fruit.yml" %}\n'
        "id: result\nmandatory: True\nquestion: |\n"
        "  Your favorite fruit is ${ favorite_fruit }.\n"
    )
    assert not any(
        f.severity == "error"
        for f in find_errors_from_string(source, input_file=str(tmp_path / "main.yml"))
    )
