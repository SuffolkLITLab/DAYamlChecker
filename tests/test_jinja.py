from pathlib import Path

import pytest

from dayamlchecker._jinja import render_yaml
from dayamlchecker.fixer import plan_file
from dayamlchecker.messages import MessageId
from dayamlchecker.yaml_structure import find_errors, find_errors_from_string, main

FIXTURES = Path(__file__).parent / "fixtures" / "jinja"


def test_includes_loops_and_normal_validation():
    path = FIXTURES / "interview.yml"
    rendered, missing = render_yaml(path.read_text(), str(path))
    assert missing == []
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
        "# use jinja\n" + source,
        [],
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


@pytest.mark.parametrize(
    "include",
    [
        '{% include "docassemble.other:data/questions/fields.yml" %}',
        '{% include "missing.yml" without context %}',
        '{% include "missing.yml" ignore missing %}',
        '{% set file = "missing.yml" %}{% include file %}',
    ],
)
def test_missing_include_skips_affected_document_only(include):
    source = (
        "# use jinja\ncode: |\n  before =\n---\n"
        "id: incomplete\nquestion: Incomplete\nfields:\n"
        + include
        + "\n---\ncode: |\n  after =\n"
    )
    rendered, missing = render_yaml(source)
    assert len(missing) == 1
    assert "fields:" not in rendered
    assert rendered.count("\n") == source.count("\n") - 1
    findings = find_errors_from_string(source)
    missing_findings = [
        f for f in findings if f.message_id == MessageId.JINJA_MISSING_INCLUDE
    ]
    errors = [f for f in findings if f.message_id != MessageId.JINJA_MISSING_INCLUDE]
    assert len(missing_findings) == 1
    assert missing_findings[0].severity == "warning"
    assert "Validation is partial" in missing_findings[0].message
    assert len(errors) == 2
    assert all(f.message_id == MessageId.PYTHON_SYNTAX_ERROR for f in errors)
    # Blanking the incomplete document must not shift subsequent locations.
    expected = find_errors_from_string(rendered)
    assert [f.line_number for f in errors] == [f.line_number for f in expected]


def test_missing_standalone_and_nested_includes(tmp_path):
    (tmp_path / "local.yml").write_text('{% include "missing.yml" %}')
    source = '# use jinja\n{% include "local.yml" %}\n---\ncode: |\n  valid = 1\n'
    findings = find_errors_from_string(source, input_file=str(tmp_path / "main.yml"))
    assert len(findings) == 1
    assert findings[0].message_id == MessageId.JINJA_MISSING_INCLUDE
    assert "missing.yml" in findings[0].message


def test_include_fallback_list_uses_existing_file(tmp_path):
    (tmp_path / "exists.yml").write_text("code: |\n  valid = 1\n")
    source = '# use jinja\n{% include ["missing.yml", "exists.yml"] %}'
    assert find_errors_from_string(source, input_file=str(tmp_path / "main.yml")) == []
    findings = find_errors_from_string(source.replace("exists.yml", "also-missing.yml"))
    assert len(findings) == 1
    assert findings[0].message_id == MessageId.JINJA_MISSING_INCLUDE
    assert "missing.yml" in findings[0].message
    assert "also-missing.yml" in findings[0].message


@pytest.mark.parametrize(
    "body",
    [
        '{% import "missing.yml" as macros %}',
        '{% from "missing.yml" import question %}',
        '{% extends "missing.yml" %}',
    ],
)
def test_missing_imports_and_parents_still_fail(tmp_path, body):
    # Also exercise failures inside an otherwise available include.
    (tmp_path / "local.yml").write_text(body)
    for source in [body, '{% include "local.yml" %}']:
        findings = find_errors_from_string(
            "# use jinja\n" + source, input_file=str(tmp_path / "main.yml")
        )
        assert len(findings) == 1
        assert findings[0].message_id == MessageId.JINJA_RENDER_ERROR


def test_missing_includes_report_once_and_ignore_unselected_branches():
    source = (
        "# use jinja\n{% for i in range(3) %}\n"
        '{% include "missing.yml" %}\n---\n{% endfor %}\n'
        '{% if false %}{% include "unused.yml" %}{% endif %}'
    )
    findings = find_errors_from_string(source)
    assert len(findings) == 1
    assert "unused.yml" not in findings[0].message


def test_partial_validation_cli_exit_status(tmp_path, capsys):
    path = tmp_path / "main.yml"
    path.write_text(
        '# use jinja\n{% include "missing.yml" %}\n---\ncode: |\n  valid = 1\n'
    )
    args = [str(path), "--no-docx-accessibility"]
    assert main(args) == 0
    assert "Validation is partial" in capsys.readouterr().out
    assert main(args + ["--max-warnings", "0"]) == 1
    path.write_text(path.read_text().replace("%}\n---", "%} # no-dayc: WG106\n---"))
    assert main(args + ["--max-warnings", "0"]) == 0
    path.write_text(path.read_text().replace("valid = 1", "broken ="))
    assert main(args) == 1


@pytest.mark.parametrize(
    "suppression", ["# no-dayc: WG106", "# no-dayc: jinja_missing_include"]
)
def test_inline_suppression_hides_only_partial_validation_warning(suppression):
    source = (
        '# use jinja\n{% include "docassemble.framework:data/questions/base.yml" %} '
        + suppression
        + "\n---\ncode: |\n  broken =\n"
    )
    findings = find_errors_from_string(source)
    assert [f.message_id for f in findings] == [MessageId.PYTHON_SYNTAX_ERROR]


def test_block_suppression_does_not_hide_other_missing_dependencies():
    source = (
        '# use jinja\n# no-dayc-block: WG106\n{% include "known.yml" %}\n'
        '---\n{% include "unexpected.yml" %}\n'
    )
    findings = find_errors_from_string(source)
    assert len(findings) == 1
    assert findings[0].code == "WG106"
    assert "unexpected.yml" in findings[0].message
    assert findings[0].line_number == 5


def test_nested_include_suppression_uses_its_own_source(tmp_path):
    included = tmp_path / "local.yml"
    included.write_text('{% include "external.yml" %} # no-dayc: WG106\n')
    source = '# use jinja\n{% include "local.yml" %}\n---\ncode: |\n  valid = 1\n'
    assert find_errors_from_string(source, input_file=str(tmp_path / "main.yml")) == []
    included.write_text('{% include "external.yml" %}\n')
    findings = find_errors_from_string(source, input_file=str(tmp_path / "main.yml"))
    assert findings[0].file_name == str(included)
    assert findings[0].line_number == 1


def test_jinja_syntax_error_suppression_uses_template_source():
    assert find_errors_from_string("# use jinja\n{% if %} # no-dayc: EG105\n") == []


def test_include_suppression_is_per_source_site_not_rendered_line():
    source = (
        '# use jinja\n{{ "\\n" * 10 }}\n'
        '{% include "external.yml" %} # no-dayc: WG106\n---\n'
        '{% include "external.yml" %}\n'
    )
    findings = find_errors_from_string(source)
    assert len(findings) == 1
    assert findings[0].code == "WG106"
    assert findings[0].line_number == 5


@pytest.mark.parametrize(
    "body",
    [
        '{% import "external.yml" as framework %}',
        '{% extends "external.yml" %}',
        "question: {{ external_setting }}",
    ],
)
def test_other_dependency_errors_require_explicit_suppression(tmp_path, body):
    path = tmp_path / "main.yml"
    args = [str(path), "--no-docx-accessibility"]
    source = "# use jinja\n" + body + "\n"
    path.write_text(source)
    assert main(args) == 1
    findings = find_errors(str(path))
    assert findings[0].code == "EG105"
    assert findings[0].severity == "error"
    path.write_text(
        source.replace("# use jinja\n", "# use jinja\n# no-dayc-block: EG105\n")
    )
    assert main(args) == 0
    assert find_errors(str(path)) == []


def test_missing_include_does_not_make_downstream_errors_nonbreaking(tmp_path):
    path = tmp_path / "main.yml"
    source = '# use jinja\n{% include "external.yml" %}\n---\ncode: |\n  broken =\n'
    path.write_text(source)
    assert main([str(path), "--no-docx-accessibility"]) == 1
    assert {f.code for f in find_errors(str(path))} == {"WG106", "EG122"}
    path.write_text(
        source.replace("code: |", "# no-dayc-block: EG122\ncode: |") + "# end\n"
    )
    assert main([str(path), "--no-docx-accessibility"]) == 0
    assert [f.code for f in find_errors(str(path))] == ["WG106"]
