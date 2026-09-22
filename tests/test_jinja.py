from dataclasses import replace
from pathlib import Path
import sys

import pytest

from dayamlchecker._jinja import JinjaRenderError, render_yaml
from dayamlchecker.fixer import plan_file
from dayamlchecker.messages import MESSAGE_DEFINITIONS, MessageId
from dayamlchecker.yaml_structure import find_errors, find_errors_from_string, main

FIXTURES = Path(__file__).parent / "fixtures" / "jinja"


def test_includes_loops_and_normal_validation():
    path = FIXTURES / "interview.yml"
    rendered, missing, _unknown = render_yaml(path.read_text(), str(path))
    assert missing == []
    assert "likes_apple" in rendered and "likes_pear" in rendered
    assert "{%" not in rendered
    assert [
        replace(finding, rendered_jinja=False) for finding in find_errors(str(path))
    ] == find_errors_from_string(rendered, input_file=str(path))
    assert not any(f.severity == "error" for f in find_errors(str(path)))


def test_included_invalid_python_is_validated(tmp_path):
    (tmp_path / "included.yml").write_text("code: |\n  broken =\n")
    path = tmp_path / "main.yml"
    path.write_text('# use jinja\n{% include "included.yml" %}\n')
    findings = find_errors(str(path))
    finding = next(f for f in findings if f.message_id == MessageId.PYTHON_SYNTAX_ERROR)
    assert finding.file_name == str(path)
    assert finding.rendered_jinja
    assert finding.line_number is not None


@pytest.mark.parametrize(
    "body, expected",
    [
        ("{% if %}", "Expected an expression"),
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


def test_server_jinja_data_is_tolerated_when_unavailable_offline():
    source = (
        "# use jinja\n"
        "{% for category in jinja_config_automatedpleading_document_categories %}\n"
        "---\nquestion: {{ category.label }}\nfield: {{ category.value }}\n"
        "{% endfor %}\n"
        "---\nid: config context\nquestion: |\n"
        "  {{ nested_config.item.helper() }}\n"
        "fields:\n  - Value: answer\n"
        "{% if __debug__ %}help: Debug mode{% endif %}\n"
    )
    rendered, missing, unknown = render_yaml(source)
    assert missing == []
    assert [u.name for u in unknown] == ["nested_config"]
    assert "question: |\n  dayc_unknown_" in rendered
    assert [f.code for f in find_errors_from_string(source)] == ["WG107"]


def test_offline_server_values_survive_arithmetic_and_comparison():
    # A `jinja data` value is often a count or a threshold. Comparing or adding
    # one must pick the empty branch, not abort the file.
    source = (
        "# use jinja\n"
        "{% if jinja_data.limit > 0 %}\n"
        "question: Configured limit\n"
        "{% else %}\n"
        "question: Answer {{ jinja_data.limit + 1 }}{{ -jinja_data.offset }}\n"
        "fields:\n  - Value: answer\n"
        "{% endif %}\n"
    )
    rendered, missing, unknown = render_yaml(source)
    assert missing == []
    assert "Configured limit" not in rendered
    assert "question: Answer" in rendered
    assert all(f.code == "WG107" for f in find_errors_from_string(source))


@pytest.mark.parametrize(
    "expression",
    [
        "{{ ''.__class__ > 1 }}",
        "{{ ''.__class__ + 1 }}",
        "{{ ''.__class__ | int }}",
        "{{ -''.__class__ }}",
    ],
)
def test_sandbox_violations_still_fail_through_offline_operators(expression):
    findings = find_errors_from_string("# use jinja\nquestion: " + expression + "\n")
    assert [f.code for f in findings] == ["EG106"]
    assert "unsafe" in findings[0].message


def test_every_failing_undefined_operator_is_covered():
    """Guard against a future Jinja adding an operator that aborts a render.

    ``Undefined`` routes a fixed set of operators to an error. Each one is a
    way a real interview could use a value the server supplies, so every one
    has to be handled here rather than found one failing file at a time.
    """
    from jinja2.runtime import Undefined

    from dayamlchecker._jinja import _OfflineUndefined

    raises = Undefined._fail_with_undefined_error
    uncovered = {
        name
        for name, attr in vars(Undefined).items()
        if attr is raises
        and getattr(_OfflineUndefined, name, None) is getattr(Undefined, name, None)
    }
    # __div__/__rdiv__ are Python 2 spellings that Python 3 never calls, and
    # _fail_with_undefined_error is the helper itself.
    assert uncovered == {"__div__", "__rdiv__", "_fail_with_undefined_error"}


@pytest.mark.parametrize(
    "body",
    [
        # Protocols that reach an undefined value without going through
        # Undefined's own operator table.
        "{{ x | abs }}",
        "{{ x | round }}",
        "{{ x | round(2) }}",
        "{{ x | tojson }}",
        "{{ {'k': x} | tojson }}",
        "{% for i in range(x) %}{{ i }}{% endfor %}",
        "{{ '{:>5}'.format(x) }}",
        # The compiler binds Jinja's strict Undefined for the implicit else of
        # an inline if, bypassing the environment's type.
        "{{ 'A' if x }}",
        "{{ (1 if x) + 1 }}",
        "{% if (1 if x) > 0 %}A{% endif %}",
        "{% block b %}{{ (1 if x) + 1 }}{% endblock %}",
        "{% macro m() %}{{ (1 if x) + 1 }}{% endmacro %}{{ m() }}",
    ],
)
def test_offline_values_survive_every_reachable_protocol(body):
    render_yaml("# use jinja\n" + body + "\n")


@pytest.mark.parametrize(
    "body",
    [
        "{{ ''.__class__ | abs }}",
        "{{ ''.__class__ | round }}",
        "{{ ''.__class__ | tojson }}",
        "{% for i in range(''.__class__) %}{{ i }}{% endfor %}",
        "{{ '{:>5}'.format(''.__class__) }}",
        "{{ 'abc'[''.__class__] }}",
        "{{ (1 if ''.__class__.__mro__) + 1 }}",
    ],
)
def test_sandbox_fails_closed_through_every_offline_protocol(body):
    findings = find_errors_from_string("# use jinja\nquestion: " + body + "\n")
    assert [f.code for f in findings] == ["EG106"]
    assert "unsafe" in findings[0].message


def test_builtin_filters_and_tests_accept_offline_values():
    """Every stock filter and test has to tolerate a server-supplied value."""
    from jinja2.sandbox import SandboxedEnvironment

    env = SandboxedEnvironment()

    def rejects(body):
        try:
            render_yaml("# use jinja\n" + body + "\n")
        except JinjaRenderError as exc:
            # Arity complaints are about the call, not the undefined value.
            return "argument" not in str(exc) and "positional" not in str(exc)
        return False

    failed = []
    for name in sorted(env.filters):
        shapes = [
            f"{{{{ x | {name} }}}}",
            f"{{{{ x | {name}(1) }}}}",
            f"{{{{ x | {name}('a') }}}}",
            f"{{{{ x | {name}('a', 'b') }}}}",
        ]
        if all(rejects(shape) for shape in shapes):
            failed.append(name)
    for name in sorted(env.tests):
        if not name.isalpha():
            continue  # operator aliases such as `>=` are not `is` syntax
        shapes = [f"{{{{ x is {name} }}}}", f"{{{{ x is {name} 1 }}}}"]
        if all(rejects(shape) for shape in shapes):
            failed.append(name)
    assert failed == []


@pytest.mark.parametrize(
    "body",
    [
        "{{ a.b.c.d }}",
        "{{ a['b'][0] }}",
        "{{ a.helper(1, k=2) }}",
        "{% if 0 < x < 10 %}A{% endif %}",
        "{% for k, v in x %}{{ k }}{% endfor %}",
        "{% for i in x %}{{ loop.index }}{{ loop.previtem }}{{ loop.nextitem }}{% endfor %}",
        "{% for i in x recursive %}{{ loop(i) }}{% endfor %}",
        "{{ x ~ 'y' }}{{ x + 1 }}{{ 1 + x }}{{ x * 2 }}{{ x / 2 }}{{ x % 2 }}{{ x ** 2 }}",
        "{{ -x }}{{ +x }}{{ not x }}{{ x and 1 }}{{ x or 2 }}",
        "{{ x == 1 }}{{ x != 1 }}{{ 1 in x }}{{ x is in [1, 2] }}",
        "{% set y = x %}{{ y }}",
        "{% set y %}{{ x }}{% endset %}{{ y }}",
        "{% with y = x %}{{ y }}{% endwith %}",
        "{% set ns = namespace(v=x) %}{% set ns.v = x %}{{ ns.v }}",
        "{% filter upper %}{{ x }}{% endfilter %}",
        "{% macro m(a, b) %}{{ a }}{{ b }}{% endmacro %}{{ m(x) }}",
        "{% macro m() %}{{ caller() }}{% endmacro %}{% call m() %}{{ x }}{% endcall %}",
        "{% macro m() %}{{ varargs }}{{ kwargs }}{% endmacro %}{{ m(x) }}",
        "{% block b %}{{ x }}{% endblock %}{{ self.b() }}",
        "{{ {'k': x} }}{{ [x, x] }}{{ x[1:3] }}",
        "{{ lipsum(x) }}",
        "{%- if x -%}A{%- else -%}B{%- endif -%}",
    ],
)
def test_jinja_constructs_tolerate_offline_values(body):
    render_yaml("# use jinja\n" + body + "\n")


def test_a_server_value_as_a_whole_scalar_does_not_break_validation():
    # These render to a null YAML value, which reaches checks that expect a
    # string. The interview is valid on a real server, so it must stay clean.
    for body in (
        "question: {{ jinja_data.text }}\n",
        "question: Hi\nsubquestion: {{ jinja_data.text }}\n",
    ):
        source = "# use jinja\nid: q\n" + body + "fields:\n  - Name: name\n"
        findings = find_errors_from_string(source, input_file="i.yml")
        assert [f.code for f in findings] == ["WG107"]


def test_unknown_value_becomes_a_unique_placeholder_warned_once_per_site():
    # One source line rendered three times is one warning, but three distinct
    # placeholders, so the generated block ids do not collide.
    source = (
        "# use jinja\n"
        "{% for i in [1, 2, 3] %}---\n"
        "id: q{{ i }}{{ jinja_data.suffix }}\n"
        "question: Q\nfields:\n  - Name: n{{ i }}\n"
        "{% endfor %}"
    )
    rendered, missing, unknown = render_yaml(source)
    assert missing == []
    assert [(u.name, u.line_number) for u in unknown] == [("jinja_data", 3)]
    ids = sorted(line for line in rendered.splitlines() if line.startswith("id:"))
    assert len(set(ids)) == 3
    assert [f.code for f in find_errors_from_string(source)] == ["WG107"]


def test_placeholder_keeps_the_surrounding_yaml_checkable():
    # Each of these renders a server value into a position where an empty
    # value would break the structure and hide everything after it.
    for body in (
        "id: q\nquestion: Hello\nfields:\n  - {{ jinja_data.label }}: name\n",
        "id: c\ncode: |\n  x = {{ jinja_data.value }}\n",
        "id: {{ jinja_data.id }}\nquestion: Hi\nfields:\n  - Name: name\n",
        "id: q\nmandatory: {{ jinja_data.m }}\nquestion: Hi\nfields:\n  - Name: name\n",
    ):
        findings = find_errors_from_string("# use jinja\n" + body, input_file="i.yml")
        assert [f.code for f in findings] == ["WG107"], body


def test_placeholder_does_not_hide_a_real_error_in_the_same_file():
    source = (
        "# use jinja\n"
        "id: q\nquestion: {{ jinja_data.title }}\nfields:\n  - Name: name\n"
        "---\nid: c\ncode: |\n  broken =\n"
    )
    codes = [f.code for f in find_errors_from_string(source, input_file="i.yml")]
    assert "WG107" in codes and "EG122" in codes


def test_placeholder_is_not_reported_as_an_unknown_screen_variable():
    source = (
        "# use jinja\nid: q\nquestion: Hi\n"
        "fields:\n  - Name: name\n    show if: {{ jinja_data.cond }}\n"
    )
    assert [f.code for f in find_errors_from_string(source, input_file="i.yml")] == [
        "WG107"
    ]


@pytest.mark.parametrize("suppression", ["inline", "block"])
def test_unknown_value_warning_suppresses_from_template_source(suppression):
    source = (
        "# use jinja\nid: q\nquestion: {{ jinja_data.t }}\nfields:\n  - Name: name\n"
    )
    findings = find_errors_from_string(source, input_file="i.yml")
    assert [(f.code, f.line_number) for f in findings] == [("WG107", 3)]
    if suppression == "inline":
        source = source.replace(
            "{{ jinja_data.t }}", "{{ jinja_data.t }} # no-dayc: WG107"
        )
    else:
        source = source.replace(
            "# use jinja\n", "# use jinja\n# no-dayc-block: WG107\n"
        )
    assert find_errors_from_string(source, input_file="i.yml") == []


def test_sandbox_violation_is_an_error_not_a_placeholder():
    findings = find_errors_from_string("# use jinja\nquestion: {{ ''.__class__ }}\n")
    assert [f.code for f in findings] == ["EG106"]


def test_render_error_code_is_not_shared_with_an_unrelated_check():
    # Suppression matches on the code string alone, so a code shared with an
    # unrelated check would silence that check too.
    render_error = MESSAGE_DEFINITIONS[MessageId.JINJA_RENDER_ERROR]
    assert render_error.code not in [
        definition.code
        for message_id, definition in MESSAGE_DEFINITIONS.items()
        if message_id != MessageId.JINJA_RENDER_ERROR
    ]


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
    rendered, missing, _unknown = render_yaml(source)
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
    assert find_errors_from_string("# use jinja\n{% if %} # no-dayc: EG106\n") == []


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
    ],
)
def test_other_dependency_errors_require_explicit_suppression(tmp_path, body):
    path = tmp_path / "main.yml"
    args = [str(path), "--no-docx-accessibility"]
    source = "# use jinja\n" + body + "\n"
    path.write_text(source)
    assert main(args) == 1
    findings = find_errors(str(path))
    assert findings[0].code == "EG106"
    assert findings[0].severity == "error"
    path.write_text(
        source.replace("# use jinja\n", "# use jinja\n# no-dayc-block: EG106\n")
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


@pytest.mark.parametrize(
    "header", ["# use jinja2", "# use jinja disabled", " # use jinja", "\n# use jinja"]
)
def test_directive_prefixes_remain_ordinary_yaml(tmp_path, header):
    path = tmp_path / "ordinary.yml"
    path.write_text(header + '\nquestion: "{{ missing }}"\nfields:\n  - Name: name\n')
    findings = find_errors(str(path))
    assert all(f.message_id != MessageId.JINJA_RENDER_ERROR for f in findings)
    assert all(not f.rendered_jinja for f in findings)
    plan = plan_file(path)
    assert plan.skipped_reason is None


@pytest.mark.parametrize("ending", ["\n", "\r\n", ""])
def test_exact_directive_is_shared_by_checker_and_fixer(tmp_path, ending):
    from dayamlchecker._jinja import uses_jinja

    source = "# use jinja" + ending
    assert uses_jinja(source)
    assert find_errors_from_string(source) == []
    path = tmp_path / "main.yml"
    path.write_bytes(source.encode())
    assert (
        plan_file(path).skipped_reason
        == "Jinja templates cannot be automatically rewritten"
    )


@pytest.mark.parametrize("expression", ["{{ 1 / 0 }}"])
@pytest.mark.parametrize("suppression", ["inline", "block"])
def test_nested_runtime_error_location_and_suppression(
    tmp_path, expression, suppression
):
    inner = tmp_path / "inner.yml"
    outer = tmp_path / "outer.yml"
    outer.write_text('{% include "inner.yml" %}\n')
    source = '# use jinja\n{% include "outer.yml" %}\n'
    inner.write_text("# comment\n" + expression + "\n")
    findings = find_errors_from_string(source, input_file=str(tmp_path / "main.yml"))
    assert len(findings) == 1
    assert findings[0].code == "EG106"
    assert findings[0].file_name == str(inner)
    assert findings[0].line_number == 2
    if suppression == "inline":
        inner.write_text("# comment\n" + expression + " # no-dayc: EG106\n")
    else:
        inner.write_text("# no-dayc-block: EG106\n" + expression + "\n")
    assert find_errors_from_string(source, input_file=str(tmp_path / "main.yml")) == []


def test_top_level_runtime_error_has_source_line():
    source = "# use jinja\nquestion: {{ 1 / 0 }}\n"
    findings = find_errors_from_string(source, input_file="unsaved.yml")
    assert findings[0].file_name == "unsaved.yml"
    assert findings[0].line_number == 2
    assert (
        find_errors_from_string(
            source.rstrip() + " # no-dayc: EG106\n", input_file="unsaved.yml"
        )
        == []
    )


def test_rendered_output_limit_is_a_finding():
    source = '# use jinja\n{% for i in range(10) %}{{ "x" * 1000000 }}{% endfor %}'
    findings = find_errors_from_string(source)
    assert len(findings) == 1
    assert findings[0].code == "EG106"
    assert "output exceeds" in findings[0].message
    # A failed worker must not poison subsequent validations.
    assert render_yaml("code: |\n  valid = 1")[0] == "code: |\n  valid = 1"


def test_render_timeout_kills_and_reaps_worker(monkeypatch):
    from dayamlchecker import _jinja

    processes = []
    real_popen = _jinja.subprocess.Popen

    def record_process(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(_jinja.subprocess, "Popen", record_process)
    monkeypatch.setattr(_jinja, "_RENDER_TIMEOUT", 0.2)
    source = (
        "# use jinja\n{% for a in range(100000) %}{% for b in range(100000) %}"
        "{% set value = a + b %}{% endfor %}{% endfor %}"
    )
    findings = find_errors_from_string(source)
    assert findings[0].code == "EG106"
    assert "time limit" in findings[0].message
    assert len(processes) == 1
    assert processes[0].poll() is not None


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="Darwin cannot lower RLIMIT_AS below the process's existing virtual size",
)
def test_large_allocation_is_confined_to_worker():
    # A single expression can allocate before generate() yields, even during
    # compilation/constant folding. The worker's OS memory limit covers both.
    findings = find_errors_from_string('# use jinja\n{{ "x" * (1024 ** 3) }}')
    assert len(findings) == 1
    assert findings[0].code == "EG106"
    assert "memory" in findings[0].message
    assert render_yaml("code: |\n  valid = 1")[1] == []


def test_source_limit_rejects_before_launching_worker(monkeypatch):
    from dayamlchecker import _jinja

    def unexpected_run(*args, **kwargs):
        pytest.fail("Oversized input should not start a worker")

    monkeypatch.setattr(_jinja.subprocess, "run", unexpected_run)
    findings = find_errors_from_string("# use jinja\n" + "x" * _jinja._MAX_SOURCE_BYTES)
    assert findings[0].code == "EG106"
    assert "source exceeds" in findings[0].message


def test_resource_limits_unavailable_fail_closed(monkeypatch):
    import sys
    from dayamlchecker import _jinja

    monkeypatch.setitem(sys.modules, "resource", None)
    with pytest.raises(_jinja.JinjaRenderError, match="requires Unix resource limits"):
        _jinja._set_resource_limits()


def test_darwin_skips_unsupported_address_space_limit(monkeypatch):
    import resource
    from dayamlchecker import _jinja

    applied = []
    monkeypatch.setattr(_jinja.sys, "platform", "darwin")
    monkeypatch.setattr(resource, "getrlimit", lambda kind: (0, resource.RLIM_INFINITY))
    monkeypatch.setattr(
        resource, "setrlimit", lambda kind, limits: applied.append(kind)
    )
    _jinja._set_resource_limits()
    assert resource.RLIMIT_AS not in applied
    assert applied == [resource.RLIMIT_CPU, resource.RLIMIT_FSIZE]
