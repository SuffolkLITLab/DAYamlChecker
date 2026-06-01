import io
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import dayamlchecker
import dayamlchecker.style as style_module
from dayamlchecker.messages import FindingClass, MessageId, Severity
from dayamlchecker.yaml_structure import RuntimeOptions, find_errors_from_string, main


def test_style_checks_are_opt_in_by_default():
    yaml_text = (
        "question: |\n"
        "  Commence the interview.\n"
        "field: user_name\n"
        "language: en\n"
    )

    findings = find_errors_from_string(yaml_text, input_file="<string_input>")

    assert all(finding.finding_class != FindingClass.STYLE for finding in findings)


def test_style_checks_report_deterministic_findings():
    yaml_text = (
        "question: |\n"
        "  Do you rent your home and do you have a written lease?\n"
        "fields:\n"
        '  - label: "Commence the interview."\n'
        "    field: FirstName\n"
        "language: en\n"
    )

    findings = find_errors_from_string(
        yaml_text,
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    message_ids = {finding.message_id for finding in findings}
    assert MessageId.STYLE_PLAIN_LANGUAGE_REPLACEMENT in message_ids
    assert MessageId.STYLE_VARIABLE_ROOT_NOT_SNAKE_CASE in message_ids
    assert MessageId.STYLE_REMOVE_LANGUAGE_EN in message_ids
    assert MessageId.STYLE_COMPOUND_QUESTION in message_ids


def test_style_choices_without_stable_values_are_errors():
    findings = find_errors_from_string(
        "question: |\n"
        "  Choose a county.\n"
        "fields:\n"
        '  - label: "County"\n'
        "    field: county\n"
        "    choices:\n"
        "      - Suffolk\n"
        "      - Middlesex\n"
        "---\n"
        "question: |\n"
        "  Choose a delivery method.\n"
        "field: delivery_method\n"
        "choices:\n"
        "  - label: Mail\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    choice_findings = [
        finding
        for finding in findings
        if finding.message_id == MessageId.STYLE_CHOICES_WITHOUT_STABLE_VALUES
    ]
    assert len(choice_findings) == 2
    assert all(finding.severity == Severity.ERROR for finding in choice_findings)


def test_style_choices_with_stable_values_are_allowed():
    findings = find_errors_from_string(
        "question: |\n"
        "  Choose a county.\n"
        "fields:\n"
        '  - label: "County"\n'
        "    field: county\n"
        "    choices:\n"
        "      - Suffolk: suffolk\n"
        "      - Middlesex: middlesex\n"
        "---\n"
        "question: |\n"
        "  Choose a delivery method.\n"
        "field: delivery_method\n"
        "choices:\n"
        "  - label: Mail\n"
        "    value: mail\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_CHOICES_WITHOUT_STABLE_VALUES
        for finding in findings
    )


def test_style_rule_severity_decisions_are_stable():
    findings = find_errors_from_string(
        "question: |\n"
        "  Commence the interview.\n"
        "field: delivery_method\n"
        "choices:\n"
        "  - Mail\n"
        "---\n"
        'code: |\n  user_message = "Please complete the form before you continue."\n',
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    severities = {
        finding.message_id: finding.severity
        for finding in findings
        if finding.message_id
        in {
            MessageId.STYLE_CHOICES_WITHOUT_STABLE_VALUES,
            MessageId.STYLE_PLAIN_LANGUAGE_REPLACEMENT,
            MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE,
        }
    }
    assert severities[MessageId.STYLE_CHOICES_WITHOUT_STABLE_VALUES] == Severity.ERROR
    assert severities[MessageId.STYLE_PLAIN_LANGUAGE_REPLACEMENT] == Severity.INFO
    assert severities[MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE] == Severity.WARNING


def test_style_llm_missing_api_key_reports_configuration_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    findings = find_errors_from_string(
        "question: |\n  Please do this now.\nfield: user_name\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_include_llm=True),
    )

    assert any(
        finding.message_id == MessageId.STYLE_LLM_CONFIGURATION_ERROR
        for finding in findings
    )


def test_style_checks_report_hardcoded_user_text_in_code():
    findings = find_errors_from_string(
        'code: |\n  user_message = "Please complete the form before you continue."\n',
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert any(
        finding.message_id == MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE
        for finding in findings
    )


def test_style_checks_ignore_multiline_code_without_hardcoded_text():
    findings = find_errors_from_string(
        "code: |\n"
        "  if url_args.get('recipient_email'):\n"
        "    recipient_email = url_args.get('recipient_email')\n"
        "  else:\n"
        '    recipient_email = ""\n',
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE
        for finding in findings
    )


def test_style_checks_ignore_lowercase_config_strings_in_code():
    findings = find_errors_from_string(
        'code: |\n  config_name = "enable weaver for unauthenticated users"\n',
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE
        for finding in findings
    )


def test_style_checks_ignore_docstrings_and_data_lists_in_code():
    findings = find_errors_from_string(
        "code: |\n"
        "  def parse_date(value):\n"
        '    """Return a valid date input string as a date, otherwise None."""\n'
        "    allowed_courts = ['Boston Municipal Court']\n"
        "    return value\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE
        for finding in findings
    )


def test_style_checks_ignore_short_f_string_fragments_in_code():
    findings = find_errors_from_string(
        "code: |\n"
        "  def job_description():\n"
        "    return f\"{job.source} {'(self-employed)' if job.is_self_employed else ('for ' + job.employer_name_address_phone())}\"\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE
        for finding in findings
    )


def test_style_checks_flag_validation_error_messages_in_code():
    findings = find_errors_from_string(
        'code: |\n  validation_error("Please choose who will mail notice of the hearing.")\n',
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert any(
        finding.message_id == MessageId.STYLE_HARDCODED_USER_TEXT_IN_CODE
        for finding in findings
    )


def test_style_compound_question_ignores_single_choice_question():
    findings = find_errors_from_string(
        "question: |\n  Do you rent or own your home?\nfield: housing_choice\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_COMPOUND_QUESTION
        for finding in findings
    )


def test_style_compound_question_flags_multiple_prompts():
    findings = find_errors_from_string(
        "question: |\n"
        "  Do you rent your home and do you have a written lease?\n"
        "field: lease_status\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert any(
        finding.message_id == MessageId.STYLE_COMPOUND_QUESTION
        for finding in findings
    )


def test_style_checks_warn_on_question_level_help():
    findings = find_errors_from_string(
        "id: intro\n"
        "question: |\n"
        "  Tell us about your case.\n"
        "help: |\n"
        "  You can find more details in the court paperwork.\n"
        "field: case_summary\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert any(
        finding.message_id == MessageId.STYLE_QUESTION_LEVEL_HELP
        for finding in findings
    )


def test_style_checks_allow_field_level_help():
    findings = find_errors_from_string(
        "id: intro\n"
        "question: |\n"
        "  Tell us about your case.\n"
        "fields:\n"
        '  - label: "Case number"\n'
        "    field: case_number\n"
        "    help: |\n"
        "      This is on the top-right corner of your notice.\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_QUESTION_LEVEL_HELP
        for finding in findings
    )


def test_style_variable_root_check_ignores_note_only_fields():
    findings = find_errors_from_string(
        "question: |\n"
        "  Tell us about your fees.\n"
        "fields:\n"
        "  - note: |\n"
        "      You do not need to tell the court the amount to waive.\n"
        "  - label: First name\n"
        "    field: user_name\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_VARIABLE_ROOT_NOT_SNAKE_CASE
        for finding in findings
    )


def test_style_llm_uses_explicit_credentials(monkeypatch):
    calls: list[dict[str, str]] = []

    def fake_call_openai_chat_completion(**kwargs):
        calls.append(kwargs)
        return (
            {
                "findings": [
                    {
                        "rule_id": "tone-and-respect",
                        "message": "This sounds too directive.",
                        "screen_id": "block-0",
                        "problematic_text": "You must do this now.",
                    }
                ]
            },
            None,
        )

    monkeypatch.setattr(
        style_module,
        "_call_openai_chat_completion",
        fake_call_openai_chat_completion,
    )

    findings = find_errors_from_string(
        "question: |\n  You must do this now.\nfield: user_name\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(
            style_include_llm=True,
            style_openai_base_url="https://example.test/v1",
            style_openai_api_key="test-key",
            style_openai_model="demo-model",
        ),
    )

    assert len(calls) == 2
    assert all(call["base_url"] == "https://example.test/v1" for call in calls)
    assert all(call["api_key"] == "test-key" for call in calls)
    assert all(call["model"] == "demo-model" for call in calls)
    assert any(
        finding.message_id == MessageId.STYLE_TONE_AND_RESPECT for finding in findings
    )


def test_style_llm_uses_environment_credentials(monkeypatch):
    calls: list[dict[str, str]] = []

    def fake_call_openai_chat_completion(**kwargs):
        calls.append(kwargs)
        return ({"findings": []}, None)

    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    monkeypatch.setattr(
        style_module,
        "_call_openai_chat_completion",
        fake_call_openai_chat_completion,
    )

    findings = find_errors_from_string(
        "question: |\n  Ready to begin?\nfield: user_name\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_include_llm=True),
    )

    assert len(calls) == 2
    assert all(call["base_url"] == "https://env.example/v1" for call in calls)
    assert all(call["api_key"] == "env-key" for call in calls)
    assert all(call["model"] == "env-model" for call in calls)
    assert all(
        finding.message_id != MessageId.STYLE_LLM_CONFIGURATION_ERROR
        for finding in findings
    )


def test_module_style_helper_returns_structured_style_findings():
    findings = dayamlchecker.find_style_findings_from_string(
        "id: intro\nquestion: |\n  Commence the interview.\nfield: user_name\n",
        input_file="<string_input>",
    )

    assert findings
    assert all(finding.finding_class == FindingClass.STYLE for finding in findings)
    assert all(finding.context.get("screen_id") == "intro" for finding in findings)


def test_main_can_run_style_checks_from_cli():
    with TemporaryDirectory() as tmp:
        interview = Path(tmp) / "style.yml"
        interview.write_text(
            "question: |\n"
            "  Commence the interview.\n"
            "field: user_name\n"
            "language: en\n",
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--style", "--no-url-check", str(interview)])

        output = stdout.getvalue().lower()
        assert exit_code == 1
        assert "[is712]" in output
        assert "[es703]" in output


def test_style_checks_report_missing_theme_and_review_edits():
    yaml_text = (
        "metadata:\n"
        "  title: Example interview\n"
        "---\n"
        "id: review_screen\n"
        "question: |\n"
        "  Review your answers\n"
        "review:\n"
        '  - label: "Name"\n'
        "---\n"
        "id: housing\n"
        "question: |\n"
        "  Do you rent your home?\n"
        "fields:\n"
        '  - label: "Rent or own"\n'
        "    field: housing_choice\n"
        "    datatype: radio\n"
        "    choices:\n"
        '      - "Rent: rent"\n'
        '      - "Own: own"\n'
    )

    findings = find_errors_from_string(
        yaml_text,
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    message_ids = {finding.message_id for finding in findings}
    assert MessageId.STYLE_MISSING_CUSTOM_THEME in message_ids
    assert MessageId.STYLE_REVIEW_SCREEN_MISSING_EDIT_LINKS in message_ids


def test_style_theme_rule_allows_explicit_theme_configuration():
    findings = find_errors_from_string(
        "metadata:\n"
        "  title: Example interview\n"
        "---\n"
        "features:\n"
        "  bootstrap theme: example-theme.css\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_MISSING_CUSTOM_THEME
        for finding in findings
    )


def test_style_preview_screen_without_review_block_is_not_review_screen():
    findings = find_errors_from_string(
        "id: preview_document\n"
        "question: |\n"
        "  Preview your document\n"
        "subquestion: |\n"
        "  Review the document before you download it.\n",
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    assert all(
        finding.message_id != MessageId.STYLE_REVIEW_SCREEN_MISSING_EDIT_LINKS
        for finding in findings
    )


def test_style_checks_report_review_choice_gaps_and_person_object_hint():
    yaml_text = (
        "id: housing\n"
        "question: |\n"
        "  Do you rent your home?\n"
        "fields:\n"
        '  - label: "Rent or own"\n'
        "    field: housing_choice\n"
        "    datatype: radio\n"
        "    choices:\n"
        '      - "Rent: rent"\n'
        '      - "Own: own"\n'
        "---\n"
        "id: review_screen\n"
        "question: |\n"
        "  Review your answers\n"
        "review:\n"
        '  - label: "Name"\n'
        '    Edit: user_name\n'
        "---\n"
        "id: names\n"
        "question: |\n"
        "  Tell us about yourself\n"
        "fields:\n"
        '  - label: "First name"\n'
        "    field: user_first_name\n"
        '  - label: "Last name"\n'
        "    field: user_last_name\n"
        '  - label: "Street address"\n'
        "    field: user_address\n"
        '  - label: "City"\n'
        "    field: user_city\n"
        '  - label: "Zip code"\n'
        "    field: user_zip\n"
    )

    findings = find_errors_from_string(
        yaml_text,
        input_file="<string_input>",
        runtime_options=RuntimeOptions(style_enabled=True),
    )

    message_ids = {finding.message_id for finding in findings}
    assert MessageId.STYLE_REVIEW_SCREEN_MISSING_KEY_CHOICE_EDITS in message_ids
    assert MessageId.STYLE_PREFER_PERSON_OBJECTS in message_ids
    person_object_findings = [
        finding
        for finding in findings
        if finding.message_id == MessageId.STYLE_PREFER_PERSON_OBJECTS
    ]
    assert person_object_findings[0].context["snippet"] == "user_first_name"
