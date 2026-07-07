from dayamlchecker._code_def_warning import PYTHON_CODE_FUNCTION_DEF
from dayamlchecker.messages import FindingClass, Severity
from dayamlchecker.yaml_structure import find_errors_from_string


def test_code_block_function_def_warns():
    findings = find_errors_from_string(
        "code: |\n"
        "  answer = 1\n"
        "  def helper():\n"
        "    return answer\n",
        input_file="<string_input>",
    )

    warning = next(
        finding
        for finding in findings
        if finding.message_id == PYTHON_CODE_FUNCTION_DEF
    )
    assert warning.severity == Severity.WARNING
    assert warning.finding_class == FindingClass.GENERAL
    assert warning.context["function_name"] == "helper"
    assert "Python module" in warning.message


def test_code_block_without_function_def_does_not_warn():
    findings = find_errors_from_string(
        "code: |\n"
        "  answer = 1\n"
        "  if answer:\n"
        "    result = answer\n",
        input_file="<string_input>",
    )

    assert all(
        finding.message_id != PYTHON_CODE_FUNCTION_DEF for finding in findings
    )
