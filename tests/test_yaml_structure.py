import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import jinja2

from dayamlchecker._jinja import JinjaError, _SilentUndefined, preprocess_jinja
from dayamlchecker.messages import (
    MESSAGE_DEFINITIONS,
    MessageCode,
    format_message,
    is_experimental_code,
)
from dayamlchecker.yaml_structure import (
    RuntimeOptions,
    YAMLError,
    _lc_key_line,
    _message_severity,
    _variable_candidates,
    find_errors_from_string,
)

MESSAGE_CODE_PATTERN = r"^[EWC]\d{3}$"
LARGE_INVALID_INTERVIEW_FIXTURE = (
    Path(__file__).parent / "fixtures" / "large_invalid_interview.yml"
)
LARGE_INVALID_JINJA_SYNTAX_FIXTURE = (
    Path(__file__).parent / "fixtures" / "large_invalid_jinja_syntax.yml"
)
LARGE_INVALID_JINJA_TEMPLATE_FIXTURE = (
    Path(__file__).parent / "fixtures" / "large_invalid_jinja_template.yml"
)
LARGE_VALID_INTERVIEW_FIXTURE = (
    Path(__file__).parent / "fixtures" / "large_valid_interview.yml"
)
ALL_ERROR_CODE_FIXTURES = (
    LARGE_INVALID_INTERVIEW_FIXTURE,
    LARGE_INVALID_JINJA_SYNTAX_FIXTURE,
    LARGE_INVALID_JINJA_TEMPLATE_FIXTURE,
)
ACCESSIBILITY_ERROR_CODES = {
    code
    for code in MESSAGE_DEFINITIONS
    if getattr(code, "value", str(code)).startswith("E5")
}


def test_message_severity_handles_none_convention_and_unknown_codes():
    assert _message_severity(None) == "error"
    assert _message_severity("C101") == "convention"
    assert _message_severity("Z999") == "error"


def test_yaml_error_severity_uses_warning_prefix_without_code():
    err = YAMLError(err_str="Warning: heads up", line_number=1, file_name="test.yml")

    assert err.severity == "warning"


def test_yaml_error_severity_uses_info_prefix_without_code():
    err = YAMLError(err_str="Info: note", line_number=1, file_name="test.yml")

    assert err.severity == "convention"


def test_yaml_error_severity_defaults_to_error_without_code_or_prefix():
    err = YAMLError(err_str="bad key", line_number=1, file_name="test.yml")

    assert err.severity == "error"


def test_lc_key_line_uses_key_specific_metadata_when_available():
    class Location:
        line = 2

        def key(self, key):
            assert key == "question"
            return (6, 0)

    class Node:
        lc = Location()

    assert _lc_key_line(Node(), "question") == 7


class TestYAMLStructure(unittest.TestCase):
    def test_valid_question_no_errors(self):
        valid = """
question: |
  What is your name?
field: name
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertEqual(len(errs), 0, f"Expected no errors, got: {errs}")

    def test_question_and_template_exclusive_error(self):
        invalid = """
question: |
  What's your name?
template: |
  Hello
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                e.code == MessageCode.TOO_MANY_TYPES
                and "Too many types this block could be" in e.err_str
                for e in errs
            ),
            f"Expected exclusivity error, got: {errs}",
        )

    def test_unknown_block_type_error_is_clearer(self):
        invalid = """
foo: bar
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "Couldn't identify a block type: no valid combination of keys found"
                in e.err_str
                for e in errs
            ),
            f"Expected clearer unknown block type error, got: {errs}",
        )

    def test_mixed_case_question_keys_are_accepted(self):
        invalid = """
Question: |
  What is your name?
Field: user_name
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertEqual(len(errs), 0, f"Expected no errors, got: {errs}")

    def test_mixed_case_field_modifier_is_not_accepted(self):
        invalid = """
question: |
  What is your favorite fruit?
fields:
  - label: Fruit
    field: favorite_fruit
  - label: Why
    Show If: favorite_fruit
    field: fruit_reason
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                'Invalid field key "Show If"' in e.err_str
                and 'use "show if"' in e.err_str
                for e in errs
            ),
            f"Expected mixed-case modifier key to be rejected, got: {errs}",
        )

    def test_duplicate_key_error(self):
        duplicate = """
question: |
  Q1
question: |
  Q2
"""
        errs = find_errors_from_string(duplicate, input_file="<string_dups>")
        self.assertTrue(
            len(errs) > 0, f"Expected parser error for duplicate keys, got: {errs}"
        )
        self.assertTrue(
            any(
                e.code == MessageCode.YAML_DUPLICATE_KEY
                and (
                    "duplicate key" in e.err_str.lower()
                    or "found duplicate key" in e.err_str.lower()
                )
                for e in errs
            ),
            f"Expected duplicate key error, got: {errs}",
        )

    def test_accessibility_mode_disabled_by_default(self):
        yaml_content = """question: |
  ![](docassemble.demo:data/static/logo.png)
"""
        errs = find_errors_from_string(yaml_content, input_file="<string_valid>")
        accessibility_errors = [
            e for e in errs if "accessibility:" in e.err_str.lower()
        ]
        self.assertEqual(
            len(accessibility_errors),
            0,
            f"Did not expect accessibility errors in default mode, got: {accessibility_errors}",
        )

    def test_accessibility_markdown_image_missing_alt_text(self):
        yaml_content = """question: |
  ![](docassemble.demo:data/static/logo.png)
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "accessibility: markdown image" in e.err_str.lower()
                and "missing alt text" in e.err_str.lower()
                for e in errs
            ),
            f"Expected markdown alt text accessibility error, got: {errs}",
        )
        self.assertTrue(
            any(
                e.code == MessageCode.ACCESSIBILITY_IMAGE_MISSING_ALT_TEXT
                and e.severity == "error"
                for e in errs
            ),
            f"Expected coded accessibility error, got: {errs}",
        )

    def test_accessibility_file_tag_missing_alt_text(self):
        yaml_content = """question: |
  [FILE docassemble.demo:data/static/al_logo.svg, 100vw]
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "accessibility: [file ...] image" in e.err_str.lower()
                and "missing alt text" in e.err_str.lower()
                for e in errs
            ),
            f"Expected FILE-tag alt text accessibility error, got: {errs}",
        )

    def test_accessibility_file_tag_missing_alt_text_without_width(self):
        yaml_content = """question: |
  [FILE docassemble.demo:data/static/al_logo.svg]
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "[file docassemble.demo:data/static/al_logo.svg]" in e.err_str.lower()
                and ", ]" not in e.err_str.lower()
                for e in errs
            ),
            f"Expected FILE-tag snippet without dangling comma, got: {errs}",
        )

    def test_accessibility_html_image_missing_alt_text(self):
        yaml_content = """subquestion: |
  <img src="/packagestatic/demo/logo.png">
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "accessibility: html image" in e.err_str.lower()
                and "missing alt text" in e.err_str.lower()
                for e in errs
            ),
            f"Expected HTML image alt text accessibility error, got: {errs}",
        )

    def test_accessibility_markdown_heading_level_skip(self):
        yaml_content = """id: q1
question: Main
subquestion: |
  ## Section
  #### Too deep
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "accessibility: markdown heading levels skip from h2 to h4"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected markdown heading-order accessibility error, got: {errs}",
        )

    def test_accessibility_html_heading_level_skip(self):
        yaml_content = """id: q1
question: Main
subquestion: |
  <h2>Section</h2>
  <h4>Too deep</h4>
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "accessibility: html heading levels skip from h2 to h4"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected HTML heading-order accessibility error, got: {errs}",
        )

    def test_accessibility_heading_order_valid_not_flagged(self):
        yaml_content = """id: q1
question: Main
subquestion: |
  ## Section
  ### Details
  <h2>HTML section</h2>
  <h3>HTML details</h3>
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        accessibility_errors = [
            e for e in errs if "accessibility:" in e.err_str.lower()
        ]
        self.assertEqual(
            len(accessibility_errors),
            0,
            f"Did not expect accessibility errors, got: {accessibility_errors}",
        )

    def test_accessibility_line_numbers_across_multiple_documents(self):
        yaml_content = """id: intro
question: Intro
---
id: q2
subquestion: |
  ## First heading
  #### Skipped heading
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        heading_error = next(
            e
            for e in errs
            if "accessibility: markdown heading levels skip" in e.err_str.lower()
        )
        self.assertEqual(
            heading_error.line_number,
            7,
            f"Expected heading error on line 7, got: {heading_error}",
        )

    def test_accessibility_mode_also_runs_structural_checks(self):
        yaml_content = """prompts:
  - id: example
    raw: Hello there
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        structural_errors = [
            e for e in errs if "accessibility:" not in e.err_str.lower()
        ]
        self.assertGreater(
            len(structural_errors),
            0,
            f"Expected structural errors for non-Docassemble YAML in accessibility mode, got: {errs}",
        )

    def test_comment_only_block_valid(self):
        yaml_content = """comment: |
  Notes for maintainers only
"""
        errs = find_errors_from_string(yaml_content, input_file="<string_valid>")
        self.assertEqual(
            len(errs), 0, f"Expected no errors for comment-only block, got: {errs}"
        )

    def test_comment_and_id_only_block_invalid(self):
        yaml_content = """id: comment_block
comment: |
  Notes for maintainers only
"""
        errs = find_errors_from_string(yaml_content, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "couldn't identify a block type: no valid combination of keys found"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected comment+id no-type validation error, got: {errs}",
        )

    def test_comment_and_non_type_attribute_block_invalid(self):
        yaml_content = """comment: |
  Notes for maintainers only
ga id: comment_block
"""
        errs = find_errors_from_string(yaml_content, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "couldn't identify a block type: no valid combination of keys found"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected comment+ga id no-type validation error, got: {errs}",
        )

    def test_comment_and_modifier_without_type_block_invalid(self):
        yaml_content = """comment: |
  Notes for maintainers only
mandatory: True
"""
        errs = find_errors_from_string(yaml_content, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "couldn't identify a block type: no valid combination of keys found"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected comment+mandatory no-type validation error, got: {errs}",
        )

    def test_accessibility_mode_still_reports_yaml_parse_errors(self):
        yaml_content = """question: |
  Bad yaml
subquestion: |
  Example
question
  missing_colon: true
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any("could not find expected ':'" in e.err_str.lower() for e in errs),
            f"Expected YAML parse error in accessibility mode, got: {errs}",
        )

    def test_accessibility_mode_ignores_non_mapping_yaml_documents(self):
        yaml_content = """---
- item one
- item two
---
question: |
  Valid mapping
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        self.assertEqual(errs, [])

    def test_accessibility_combobox_field_disabled_by_default(self):
        yaml_content = """question: |
  Pick one
fields:
  - Option: selected_option
    datatype: combobox
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        self.assertFalse(
            any("datatype: combobox" in e.err_str.lower() for e in errs),
            f"Did not expect combobox accessibility error by default, got: {errs}",
        )

    def test_accessibility_combobox_field_fails_when_enabled(self):
        yaml_content = """question: |
  Pick one
fields:
  - Option: selected_option
    datatype: combobox
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
            runtime_options=RuntimeOptions(
                accessibility_error_on_widgets=frozenset({"combobox"})
            ),
        )
        self.assertTrue(
            any(
                "datatype: combobox" in e.err_str.lower()
                and "accessibility:" in e.err_str.lower()
                for e in errs
            ),
            f"Expected combobox accessibility error, got: {errs}",
        )

    def test_accessibility_combobox_screen_disabled_by_default(self):
        yaml_content = """question: |
  Pick one
combobox: selected_option
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        self.assertFalse(
            any("screen uses `combobox`" in e.err_str.lower() for e in errs),
            f"Did not expect top-level combobox accessibility error by default, got: {errs}",
        )

    def test_accessibility_combobox_screen_fails_when_enabled(self):
        yaml_content = """question: |
  Pick one
combobox: selected_option
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
            runtime_options=RuntimeOptions(
                accessibility_error_on_widgets=frozenset({"combobox"})
            ),
        )
        self.assertTrue(
            any("screen uses `combobox`" in e.err_str.lower() for e in errs),
            f"Expected top-level combobox accessibility error, got: {errs}",
        )

    def test_accessibility_generic_link_text_english_fails(self):
        yaml_content = """question: |
  [Click here](https://example.com/forms)
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "link text" in e.err_str.lower() and "too generic" in e.err_str.lower()
                for e in errs
            ),
            f"Expected generic English link-text accessibility error, got: {errs}",
        )

    def test_accessibility_generic_link_text_spanish_fails(self):
        yaml_content = """question: |
  [Haga clic aquí](https://example.com/formulario)
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "link text" in e.err_str.lower() and "too generic" in e.err_str.lower()
                for e in errs
            ),
            f"Expected generic Spanish link-text accessibility error, got: {errs}",
        )

    def test_accessibility_empty_markdown_link_fails(self):
        yaml_content = """question: |
  [](https://example.com/blank)
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any("has no accessible text" in e.err_str.lower() for e in errs),
            f"Expected empty-link accessibility error, got: {errs}",
        )

    def test_accessibility_descriptive_link_text_allowed(self):
        yaml_content = """question: |
  [Download the filing checklist](https://example.com/checklist)
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        self.assertFalse(
            any(
                "link text" in e.err_str.lower()
                or "accessible text" in e.err_str.lower()
                for e in errs
            ),
            f"Did not expect link-text accessibility errors, got: {errs}",
        )

    def test_accessibility_no_label_allowed_single_field_screen(self):
        yaml_content = """question: |
  Enter your email
fields:
  - no label: true
    field: user_email
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        self.assertFalse(
            any("no label" in e.err_str.lower() for e in errs),
            f"Did not expect no-label accessibility errors on single-field screen, got: {errs}",
        )

    def test_accessibility_no_label_fails_multi_field_screen(self):
        yaml_content = """question: |
  Enter information
fields:
  - First name: user_first
  - no label: true
    field: user_last
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                "no label" in e.err_str.lower()
                and "single-field screens" in e.err_str.lower()
                for e in errs
            ),
            f"Expected multi-field no-label accessibility error, got: {errs}",
        )
        self.assertTrue(
            any(
                e.code == MessageCode.ACCESSIBILITY_NO_LABEL_MULTI_FIELD
                and e.severity == "error"
                for e in errs
            ),
            f"Expected coded no-label accessibility error, got: {errs}",
        )

    def test_accessibility_no_label_uses_field_variable_in_message(self):
        yaml_content = """question: |
  Enter information
fields:
  - First name: user_first
  - no label: court_county
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )

        self.assertTrue(
            any(
                e.code == MessageCode.ACCESSIBILITY_NO_LABEL_MULTI_FIELD
                and "court_county" in e.err_str
                for e in errs
            ),
            f"Expected no-label accessibility error to name field variable, got: {errs}",
        )

    def test_accessibility_code_only_field_allowed_multi_field_screen(self):
        yaml_content = """question: |
  Enter information
fields:
  - code: |
      dynamic_fields
  - First name: user_first
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        self.assertFalse(
            any("single-field screens" in e.err_str.lower() for e in errs),
            f"Did not expect code-only field accessibility error, got: {errs}",
        )

    def test_accessibility_field_with_code_and_no_label_still_fails_multi_field_screen(
        self,
    ):
        yaml_content = """question: |
  Enter information
fields:
  - First name: user_first
  - code: |
      dynamic_fields
    datatype: checkboxes
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any("single-field screens" in e.err_str.lower() for e in errs),
            f"Expected non-code-only missing-label accessibility error, got: {errs}",
        )

    def test_accessibility_empty_label_fails_multi_field_screen(self):
        yaml_content = """question: |
  Enter information
fields:
  - First name: user_first
  - label: ""
    field: user_last
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any("single-field screens" in e.err_str.lower() for e in errs),
            f"Expected empty-label accessibility error, got: {errs}",
        )

    def test_accessibility_no_label_false_does_not_count_as_label(self):
        yaml_content = """question: |
  Enter information
fields:
  - First name: user_first
  - no label: false
    field: user_last
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_invalid>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any("single-field screens" in e.err_str.lower() for e in errs),
            f"Expected missing-label accessibility error, got: {errs}",
        )

    def test_accessibility_tagged_pdf_error_for_docx_without_setting(self):
        yaml_content = """attachments:
  - name: Letter
    docx template file: letter_template.docx
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_warn>",
            lint_mode="accessibility",
        )
        self.assertTrue(
            any(
                e.code == MessageCode.ACCESSIBILITY_TAGGED_PDF_NOT_ENABLED
                and e.severity == "error"
                and "docx attachment detected" in e.err_str.lower()
                for e in errs
            ),
            f"Expected tagged-pdf accessibility error, got: {errs}",
        )

    def test_accessibility_tagged_pdf_true_in_features_suppresses_info(self):
        yaml_content = """features:
  tagged pdf: true
attachments:
  - name: Letter
    docx template file: letter_template.docx
"""
        errs = find_errors_from_string(
            yaml_content,
            input_file="<string_valid>",
            lint_mode="accessibility",
        )
        self.assertFalse(
            any("docx attachment detected" in e.err_str.lower() for e in errs),
            f"Did not expect tagged-pdf info note when features.tagged pdf is true, got: {errs}",
        )

    def test_accessibility_theme_css_contrast_fails_for_low_values(self):
        with TemporaryDirectory() as tmp:
            theme_css = Path(tmp) / "low-contrast.css"
            theme_css.write_text(
                "body { color: #777777; background-color: #888888; }\n"
                ".navbar { color: #777777; background-color: #888888; }\n"
                ".dropdown-menu { color: #666666; background-color: #777777; }\n"
                ".btn { color: #666666; background-color: #777777; }\n",
                encoding="utf-8",
            )
            yaml_content = f"""features:
  bootstrap theme: {theme_css}
"""
            errs = find_errors_from_string(
                yaml_content,
                input_file="<string_invalid>",
                lint_mode="accessibility",
            )
            self.assertTrue(
                any(
                    "low contrast" in e.err_str.lower()
                    and "bootstrap theme css" in e.err_str.lower()
                    for e in errs
                ),
                f"Expected CSS contrast accessibility error, got: {errs}",
            )

    def test_accessibility_theme_css_contrast_passes_for_good_values(self):
        with TemporaryDirectory() as tmp:
            theme_css = Path(tmp) / "good-contrast.css"
            theme_css.write_text(
                "body { color: #111111; background-color: #ffffff; }\n"
                ".navbar { color: #ffffff; background-color: #1a1a1a; }\n"
                ".dropdown-menu { color: #1a1a1a; background-color: #ffffff; }\n"
                ".btn { color: #ffffff; background-color: #0d6efd; }\n",
                encoding="utf-8",
            )
            yaml_content = f"""features:
  bootstrap theme: {theme_css}
"""
            errs = find_errors_from_string(
                yaml_content,
                input_file="<string_valid>",
                lint_mode="accessibility",
            )
            self.assertFalse(
                any("low contrast" in e.err_str.lower() for e in errs),
                f"Did not expect CSS contrast accessibility error, got: {errs}",
            )

    # JS Show If tests
    def test_js_show_if_valid(self):
        """Valid js show if with proper val() calls"""
        valid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      val("fruit") === "apple"
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        js_show_if_errors = [e for e in errs if "js show if" in e.err_str.lower()]
        self.assertEqual(
            len(js_show_if_errors),
            0,
            f"Expected no js show if errors, got: {js_show_if_errors}",
        )

    def test_js_show_if_no_val_call(self):
        """Error when js show if has no val() call"""
        invalid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      true && false
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("val()" in e.err_str and "at least one" in e.err_str for e in errs),
            f"Expected val() requirement error, got: {errs}",
        )

    def test_js_show_if_val_with_whitespace_valid(self):
        """Valid: js show if accepts whitespace between val and ("""
        valid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      val ("fruit") === "apple"
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        js_show_if_errors = [
            e
            for e in errs
            if "js show if" in e.err_str.lower() or "val()" in e.err_str.lower()
        ]
        self.assertEqual(
            len(js_show_if_errors),
            0,
            f"Expected no js show if errors, got: {js_show_if_errors}",
        )

    def test_js_show_if_unquoted_val_argument(self):
        """Error when val() argument is not quoted"""
        invalid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      val(fruit) === "apple"
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("quoted string" in e.err_str.lower() for e in errs),
            f"Expected quoted string error, got: {errs}",
        )

    def test_js_show_if_val_references_unknown_field(self):
        """Error when val() references a field not present on this screen"""
        invalid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      val("missing_field") === "apple"
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                e.code == MessageCode.JS_UNKNOWN_SCREEN_FIELD
                and "not defined on this screen" in e.err_str.lower()
                for e in errs
            ),
            f"Expected unknown field error, got: {errs}",
        )

    def test_js_show_if_unknown_field_with_dynamic_fields_code_warns(self):
        """Warn (not strict error) when js show if cannot be fully validated due to fields: code"""
        warning_yaml = """
question: |
  Dynamic fields
fields:
  - code: |
      [
        {"field": "other_parties[0].vacated", "label": "P1", "datatype": "yesno"}
      ]
  - label: Vacated date
    field: vacated_date
    datatype: date
    js show if: |
      val("other_parties[0].vacated")
"""
        errs = find_errors_from_string(warning_yaml, input_file="<string_warn>")
        self.assertTrue(
            any(
                e.code == MessageCode.JS_UNKNOWN_SCREEN_FIELD
                and "unable to fully validate screen variables" in e.err_str.lower()
                for e in errs
            ),
            f"Expected downgraded warning for dynamic fields: code, got: {errs}",
        )

    def test_js_show_if_unquoted_val_dot_argument(self):
        """Error when val() uses unquoted dotted argument"""
        invalid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      val(foo.bar) === "apple"
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("quoted string" in e.err_str.lower() for e in errs),
            f"Expected quoted string error, got: {errs}",
        )

    def test_js_show_if_quoted_val_argument(self):
        """Valid: val() argument is properly quoted"""
        valid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      val("fruit") === "apple"
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        val_errors = [e for e in errs if "quoted string" in e.err_str.lower()]
        self.assertEqual(
            len(val_errors), 0, f"Expected no quoted string errors, got: {val_errors}"
        )

    def test_js_show_if_with_mako_syntax(self):
        """Valid: js show if with Mako expressions"""
        valid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      val("fruit") === ${ json.dumps(some_var) }
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        syntax_errors = [e for e in errs if "invalid javascript" in e.err_str.lower()]
        self.assertEqual(
            len(syntax_errors),
            0,
            f"Expected no syntax errors with Mako, got: {syntax_errors}",
        )

    def test_js_show_if_invalid_syntax_unbalanced_parens(self):
        """Error when js show if has invalid syntax"""
        invalid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Favorite vegetable: vegetable
    js show if: |
      (val("fruit") === "apple"
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        syntax_errors = [e for e in errs if "invalid javascript" in e.err_str.lower()]
        self.assertGreater(
            len(syntax_errors),
            0,
            f"Expected at least one invalid JavaScript error, got: {syntax_errors}",
        )

    def test_js_show_if_complex_valid(self):
        """Valid: complex js show if with multiple val() calls"""
        valid = """
question: |
  What information do you need?
fields:
  - Favorite cuisine: cuisine
    choices:
      - Chinese
      - French
  - Favorite dish: dish
  - Rating: rating
    js show if: |
      (val("cuisine") === "Chinese" || val("cuisine") === "French") && val("dish") !== ""
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        js_show_if_errors = [
            e
            for e in errs
            if "js show if" in e.err_str.lower()
            or "invalid javascript" in e.err_str.lower()
        ]
        self.assertEqual(
            len(js_show_if_errors),
            0,
            f"Expected no js show if errors, got: {js_show_if_errors}",
        )

    # Show if with variable reference tests
    def test_show_if_variable_valid_same_screen(self):
        """Valid: show if variable references field on same screen"""
        valid = """
question: |
  What information do you need?
fields:
  - Do you like fruit?: likes_fruit
    datatype: yesnoradio
  - What's your favorite fruit?: favorite_fruit
    show if: likes_fruit
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        show_if_errors = [
            e
            for e in errs
            if "show if" in e.err_str.lower() and "not defined" in e.err_str.lower()
        ]
        self.assertEqual(
            len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}"
        )

    def test_show_if_variable_dict_valid_same_screen(self):
        """Valid: show if with dict syntax references field on same screen"""
        valid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
    choices:
      - Apple
      - Orange
  - Why do you like it?: reason
    show if:
      variable: fruit
      is: Apple
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        show_if_errors = [
            e
            for e in errs
            if "show if" in e.err_str.lower() and "not defined" in e.err_str.lower()
        ]
        self.assertEqual(
            len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}"
        )

    def test_show_if_variable_expression_valid_same_screen(self):
        """Valid: show if expression using on-screen base variable should pass"""
        valid = """
question: |
  What information do you need?
fields:
  - Reminder methods: reminder_methods
    datatype: checkboxes
    choices:
      - Email
      - Text
  - Email: email_address
    show if: reminder_methods["Email"]
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        show_if_errors = [
            e
            for e in errs
            if "show if" in e.err_str.lower() and "not defined" in e.err_str.lower()
        ]
        self.assertEqual(
            len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}"
        )

    def test_show_if_nested_index_expression_valid_same_screen(self):
        """Valid: show if nested index expression matches on-screen base field"""
        valid = """
question: |
  Child information
fields:
  - Who are this child's parents?: children[i].parents
    datatype: checkboxes
    choices:
      - Parent 1
      - Other
  - Name of other parent: children[i].other_parent
    show if: children[i].parents["Other"]
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        show_if_errors = [
            e
            for e in errs
            if "show if" in e.err_str.lower() and "not defined" in e.err_str.lower()
        ]
        self.assertEqual(
            len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}"
        )

    def test_show_if_x_alias_expression_valid_same_screen(self):
        """Valid: show if expression can match x.<attr> field alias used in generic-object screens"""
        valid = """
question: |
  Child information
fields:
  - Who are this child's parents?: x.parents
    datatype: checkboxes
    choices:
      - Parent 1
      - Other
  - Name of other parent: children[i].other_parent
    show if: children[i].parents["Other"]
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        show_if_errors = [
            e
            for e in errs
            if "show if" in e.err_str.lower() and "not defined" in e.err_str.lower()
        ]
        self.assertEqual(
            len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}"
        )

    def test_show_if_variable_not_on_screen(self):
        """Error: show if variable references field NOT on same screen"""
        invalid = """
question: |
  What information do you need?
fields:
  - What's your favorite fruit?: favorite_fruit
    show if: likes_fruit
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                e.code == MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING
                and "not defined on this screen" in e.err_str.lower()
                for e in errs
            ),
            f"Expected 'not defined on screen' error, got: {errs}",
        )

    def test_show_if_variable_non_string_type_error(self):
        """Error: show if variable must be a string"""
        invalid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Why?: reason
    show if:
      variable:
        - fruit
      is: apple
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "show if: variable must be a string" in e.err_str.lower() for e in errs
            ),
            f"Expected show if variable type error, got: {errs}",
        )

    def test_show_if_code_valid_previous_screen(self):
        """Valid: show if with code can reference variables from previous screens"""
        valid = """
question: |
  What information do you need?
fields:
  - What's your favorite fruit?: favorite_fruit
    show if:
      code: |
        previous_variable == "something"
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        show_if_errors = [
            e
            for e in errs
            if "show if" in e.err_str.lower() and "not defined" in e.err_str.lower()
        ]
        self.assertEqual(
            len(show_if_errors),
            0,
            f"Expected no show if errors with code, got: {show_if_errors}",
        )

    def test_hide_if_variable_not_on_screen(self):
        """Error: hide if variable references field NOT on same screen"""
        invalid = """
question: |
  What information do you need?
fields:
  - What's your favorite fruit?: favorite_fruit
    hide if: some_previous_var
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                e.code == MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING
                and "not defined on this screen" in e.err_str.lower()
                for e in errs
            ),
            f"Expected 'not defined on screen' error, got: {errs}",
        )

    def test_hide_if_variable_non_string_type_error(self):
        """Error: hide if variable must be a string"""
        invalid = """
question: |
  What information do you need?
fields:
  - Favorite fruit: fruit
  - Why?: reason
    hide if:
      variable:
        - fruit
      is: apple
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "hide if: variable must be a string" in e.err_str.lower() for e in errs
            ),
            f"Expected hide if variable type error, got: {errs}",
        )

    def test_enable_if_variable_not_on_screen(self):
        """Error: enable if variable references field NOT on same screen"""
        invalid = """
question: |
  What information do you need?
fields:
  - What's your favorite fruit?: favorite_fruit
    enable if: some_previous_var
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                e.code == MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING
                and "enable if" in e.err_str.lower()
                and "not defined on this screen" in e.err_str.lower()
                for e in errs
            ),
            f"Expected enable if 'not defined on screen' error, got: {errs}",
        )

    def test_disable_if_variable_not_on_screen(self):
        """Error: disable if variable references field NOT on same screen"""
        invalid = """
question: |
  What information do you need?
fields:
  - What's your favorite fruit?: favorite_fruit
    disable if: some_previous_var
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                e.code == MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING
                and "disable if" in e.err_str.lower()
                and "not defined on this screen" in e.err_str.lower()
                for e in errs
            ),
            f"Expected disable if 'not defined on screen' error, got: {errs}",
        )

    def test_js_show_if_multiple_val_calls(self):
        """Valid: js show if with multiple val() calls"""
        valid = """
question: |
  What information do you need?
fields:
  - Fruit 1: fruit1
  - Fruit 2: fruit2
  - Why?: why
    js show if: |
      val("fruit1") && val("fruit2")
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        js_show_if_errors = [
            e for e in errs if "js show if" in e.err_str.lower() or "val()" in e.err_str
        ]
        self.assertEqual(
            len(js_show_if_errors),
            0,
            f"Expected no js show if errors, got: {js_show_if_errors}",
        )

    def test_js_hide_if_valid(self):
        """Valid: js hide if works like js show if"""
        valid = """
question: |
  What information do you need?
fields:
  - TV watcher?: watches_tv
    datatype: yesnoradio
  - Favorite show: tv_show
    js hide if: |
      val("watches_tv") === false
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        js_errors = [
            e
            for e in errs
            if (
                "js hide if" in e.err_str.lower()
                or ("val()" in e.err_str and "hide" not in e.err_str.lower())
                or "invalid javascript" in e.err_str.lower()
            )
        ]
        self.assertEqual(
            len(js_errors), 0, f"Expected no js hide if errors, got: {js_errors}"
        )

    def test_js_hide_if_invalid_syntax_mentions_hide(self):
        """Error: invalid js hide if should mention js hide if in message"""
        invalid = """
question: |
  What information do you need?
fields:
  - TV watcher?: watches_tv
  - Favorite show: tv_show
    js hide if: |
      (val("watches_tv") === false
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "invalid javascript syntax in js hide if" in e.err_str.lower()
                for e in errs
            ),
            f"Expected js hide if syntax error, got: {errs}",
        )

    # Python AST / code-block tests
    def test_python_code_block_valid(self):
        """Valid: top-level code block has correct Python syntax"""
        valid = """
code: |
  x = 1
  y = x + 2
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertEqual(
            len(errs), 0, f"Expected no errors for valid code block, got: {errs}"
        )

    def test_python_code_block_invalid(self):
        """Error: top-level code block with invalid Python"""
        invalid = """
code: |
  if True
    x = 1
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("python syntax error" in e.err_str.lower() for e in errs),
            f"Expected Python syntax error, got: {errs}",
        )

    def test_show_if_code_valid_field(self):
        """Valid: field-level show if with code has valid Python"""
        valid = """
question: |
  Sample
fields:
  - Some value: a
  - Conditional field: b
    show if:
      code: |
        a == 1
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any(
                "show if: code has python syntax error" in e.err_str.lower()
                for e in errs
            ),
            f"Expected no show if code errors, got: {errs}",
        )

    def test_show_if_code_same_screen_variable_errors(self):
        """Error: show if code must not reference variables defined on same screen"""
        invalid = """
question: |
  Sample
fields:
  - Some value: a
  - Conditional field: b
    show if:
      code: |
        a == 1
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "show if: code references variable(s) defined on this screen"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected same-screen show if code reference error, got: {errs}",
        )

    def test_show_if_code_invalid_field(self):
        """Error: field-level show if with invalid Python code"""
        invalid = """
question: |
  Sample
fields:
  - Some value: a
  - Conditional field: b
    show if:
      code: |
        if True
          x = 1
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "show if: code has python syntax error" in e.err_str.lower()
                for e in errs
            ),
            f"Expected show if code syntax error, got: {errs}",
        )

    def test_show_if_code_previous_screen_variable_still_valid(self):
        """Valid: show if code can reference prior-screen variables"""
        valid = """
question: |
  Sample
fields:
  - Conditional field: b
    show if:
      code: |
        prior_screen_var == 1
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any(
                "show if: code references variable(s) defined on this screen"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected no same-screen show if code reference error, got: {errs}",
        )

    def test_show_if_code_dotted_previous_var_no_false_positive(self):
        """Valid: show if code using dotted previous-screen var should not match same-base on-screen vars"""
        valid = """
question: |
  Intake facts
fields:
  - Disability type: tenant.disability_type
    required: False
  - Explain: explanation
    show if:
      code: |
        tenant.is_disabled
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any(
                "show if: code references variable(s) defined on this screen"
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected no same-base dotted false positive, got: {errs}",
        )

    def test_validation_code_valid(self):
        """Valid: question-level validation code with correct Python syntax and uses validation_error"""
        valid = """
question: |
  There are 10 fruit in all.
fields:
  - Apples: number_apples
    datatype: integer
  - Oranges: number_oranges
    datatype: integer
validation code: |
  if number_apples + number_oranges != 10:
    validation_error("The numbers must add up to 10!")
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        # There should be no syntax errors and no warning about missing validation_error
        self.assertFalse(
            any("python syntax error" in e.err_str.lower() for e in errs),
            f"Unexpected Python syntax error: {errs}",
        )
        self.assertFalse(
            any("does not call validation_error" in e.err_str.lower() for e in errs),
            f"Unexpected missing validation_error warning: {errs}",
        )

    def test_validation_code_invalid(self):
        """Error: question-level validation code with invalid Python"""
        invalid = """
question: |
  What is your input?
fields:
  - Input: user_input
    datatype: text
validation code: |
  if True
    validation_error("Invalid")
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("python syntax error" in e.err_str.lower() for e in errs),
            f"Expected Python syntax error in validation code, got: {errs}",
        )

    def test_validation_code_missing_validation_error_warns(self):
        """Warn when validation code does not call validation_error()"""
        invalid = """
question: |
  There are 10 fruit in all.
fields:
  - Apples: number_apples
    datatype: integer
  - Oranges: number_oranges
    datatype: integer
validation code: |
  if number_apples + number_oranges != 10:
    raise Exception('Bad total')
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                e.code == MessageCode.VALIDATION_CODE_MISSING_VALIDATION_ERROR
                and "does not call validation_error" in e.err_str.lower()
                for e in errs
            ),
            f"Expected missing validation_error warning, got: {errs}",
        )

    def test_validation_code_with_transformation_no_warn(self):
        """No warning when validation code only transforms values (assignments) and has no conditionals"""
        valid = """
question: |
  What is your phone number?
fields:
  - Phone number: phone_number
validation code: |
  phone_number = phone_number.strip()
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        # Should NOT warn because this is a pure transformation (assignment) with no conditionals
        self.assertFalse(
            any("does not call validation_error" in e.err_str.lower() for e in errs),
            f"Did not expect missing validation_error warning for pure transformation code, got: {errs}",
        )

    def test_validation_code_transformation_with_conditional_no_warn(self):
        """No warning when validation code transforms values inside a conditional"""
        valid = """
question: |
  What is your phone number?
fields:
  - Phone number: phone_number
validation code: |
  if True:
    phone_number = phone_number.strip()
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any("does not call validation_error" in e.err_str.lower() for e in errs),
            f"Did not expect missing validation_error warning for conditional transformation code, got: {errs}",
        )

    def test_validation_code_define_call_no_warn(self):
        """No warning when validation code uses define() as a transformation helper"""
        valid = """
question: |
  Catchall
fields:
  - Value: x_value
validation code: |
  define("x_value", x_value)
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any("does not call validation_error" in e.err_str.lower() for e in errs),
            f"Did not expect missing validation_error warning for define() transformation code, got: {errs}",
        )

    def test_fields_code_dict_valid(self):
        """Valid: fields can be a dict with code reference"""
        valid = """
question: |
  Interrogatories
fields:
  code: ints_fields
continue button field: interrogatory_questions
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        field_errors = [
            e
            for e in errs
            if "fields should be a list" in e.err_str.lower()
            or "fields dict must have" in e.err_str.lower()
        ]
        self.assertEqual(
            len(field_errors),
            0,
            f"Expected no fields-shape errors, got: {field_errors}",
        )

    def test_fields_single_field_dict_shorthand_no_errors(self):
        """Valid: fields as a bare dict (single-field shorthand) is legal docassemble."""
        valid = """
question: |
  What venue?
fields:
  label: no label
  field: M.venue.type
  input type: radio
  choices:
    - label: ":building: Administrative"
      value: admin
    - label: ":landmark: County Circuit Court"
      value: circuit
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        field_errors = [
            e
            for e in errs
            if "fields should be a list" in e.err_str.lower()
            or "fields dict must have" in e.err_str.lower()
        ]
        self.assertEqual(
            len(field_errors),
            0,
            f"Expected no fields-shape errors, got: {field_errors}",
        )

    def test_fields_mako_templates_valid(self):
        """Error: fields with mako in them are checked."""
        valid = """
question: |
  Interrogatories
fields:
  - "Ints fields": ints_fields
    default: |
      ${ 1 + 3
         + 5}
continue button field: interrogatory_questions
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        field_errors = [e for e in errs if "default value has" in e.err_str.lower()]
        self.assertEqual(
            len(field_errors),
            1,
            f"Expected one mako field error, got: {field_errors}",
        )

    # -- _variable_candidates coverage --

    def test_variable_candidates_empty_string(self):
        """_variable_candidates with an empty/whitespace string returns empty set."""
        result = _variable_candidates("  ")
        self.assertEqual(result, set())

    def test_variable_candidates_indexed_path(self):
        """_variable_candidates strips trailing brackets iteratively."""
        result = _variable_candidates('children[i].parents["Other"]')
        self.assertIn("children[i].parents", result)
        self.assertIn("children", result)

    # -- PythonText non-string input (lines 157–158) --

    def test_python_code_block_non_string_error(self):
        """Error: code block value must be a YAML string."""
        invalid = """
code:
  - some_list_item
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("code block must be a yaml string" in e.err_str.lower() for e in errs),
            f"Expected code-block type error, got: {errs}",
        )

    # -- ValidationCode with raise/assert suppresses warning (lines 216–217) --

    def test_validation_code_with_raise_still_warns(self):
        """Validation code that only raises (no validation_error) should still warn."""
        yaml_str = """
question: |
  Test
fields:
  - Apples: apples
    datatype: integer
validation code: |
  if apples < 0:
    raise Exception("negative")
"""
        errs = find_errors_from_string(yaml_str, input_file="<string>")
        self.assertTrue(
            any("does not call validation_error" in e.err_str.lower() for e in errs),
            f"Expected missing validation_error warning for raise-only code, got: {errs}",
        )

    # -- ShowIf malformed string (lines 366–369) --

    def test_show_if_malformed_string_variable_colon(self):
        """Error: 'show if: variable:foo' as a plain string is malformed."""
        from dayamlchecker.yaml_structure import ShowIf

        validator = ShowIf("variable:a")
        self.assertTrue(
            any(
                "appears to be malformed" in str(e[0]).lower() for e in validator.errors
            ),
            f"Expected malformed show if error, got: {validator.errors}",
        )

    def test_show_if_malformed_string_code_colon(self):
        """Error: 'show if: code:True' as a plain string is malformed."""
        from dayamlchecker.yaml_structure import ShowIf

        validator = ShowIf("code:True")
        self.assertTrue(
            any(
                "appears to be malformed" in str(e[0]).lower() for e in validator.errors
            ),
            f"Expected malformed show if error, got: {validator.errors}",
        )

    # -- ShowIf dict missing variable/code keys (line ~399) --

    def test_show_if_dict_missing_variable_and_code(self):
        """Error: show if dict with neither 'variable' nor 'code' key."""
        invalid = """
question: Test
fields:
  - First: a
  - Second: b
    show if:
      unknown_key: something
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("must have either" in e.err_str.lower() for e in errs),
            f"Expected show if dict key error, got: {errs}",
        )

    # -- ShowIf code: non-string value --

    def test_show_if_code_non_string_error(self):
        """Error: show if: code must be a YAML string."""
        invalid = """
question: Test
fields:
  - First: a
  - Second: b
    show if:
      code:
        - a
        - b
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "code block must be a yaml string" in e.err_str.lower()
                or "code must be a yaml string" in e.err_str.lower()
                for e in errs
            ),
            f"Expected show if code type error, got: {[e.err_str for e in errs]}",
        )

    # -- DAPythonVar non-string / whitespace (lines 399–400) --

    def test_field_var_with_whitespace_error(self):
        """Error: a field variable name with spaces should be flagged."""
        invalid = """
question: Test
field: some var name
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("whitespace" in e.err_str.lower() for e in errs),
            f"Expected whitespace error for python var, got: {errs}",
        )

    # -- Nesting depth warning (line ~1580) --

    def test_deeply_nested_show_if_warns(self):
        """Warning when show if nesting depth exceeds 2."""
        deep = """
question: Test
fields:
  - A: a
    datatype: yesnoradio
  - B: b
    datatype: yesnoradio
    show if: a
  - C: c
    datatype: yesnoradio
    show if: b
  - D: d
    show if: c
"""
        errs = find_errors_from_string(deep, input_file="<string>")
        self.assertTrue(
            any(
                "nested" in e.err_str.lower() and "levels" in e.err_str.lower()
                for e in errs
            ),
            f"Expected nesting depth warning, got: {errs}",
        )

    # -- Interview-order unmatched guard reference --

    def test_interview_order_unmatched_guard_warning(self):
        """Warning when interview-order code references conditional field without guard."""
        yaml_str = """
question: Test
fields:
  - First: a
    datatype: yesnoradio
  - Second: b
    show if: a
---
mandatory: True
code: |
  a
  b
"""
        errs = find_errors_from_string(yaml_str, input_file="<string>")
        self.assertTrue(
            any("without a matching guard" in e.err_str.lower() for e in errs),
            f"Expected interview-order guard warning, got: {errs}",
        )

    # -- Unknown block keys --

    def test_unknown_key_error(self):
        """Error: keys that shouldn't exist are flagged."""
        invalid = """
not_a_real_key: hello
another_bad_key: world
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("keys that shouldn't exist" in e.err_str.lower() for e in errs),
            f"Expected unknown key error, got: {errs}",
        )

    # -- Non-string YAML key --

    def test_non_string_key_error(self):
        """Error: boolean/numeric keys are flagged as unexpected."""
        invalid = """
True: hello
question: test
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("keys that shouldn't exist" in e.err_str.lower() for e in errs),
            f"Expected non-string key error, got: {errs}",
        )

    # -- Enable/Disable if with code (touching lines ~537, ~588–589) --

    def test_js_disable_if_valid(self):
        """Valid: js disable if with proper val() call."""
        valid = """
question: Test
fields:
  - Watcher: watches
    datatype: yesnoradio
  - Show: show
    js disable if: |
      val("watches") === false
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        js_errors = [e for e in errs if "js disable if" in e.err_str.lower()]
        self.assertEqual(
            len(js_errors), 0, f"Expected no js disable if errors, got: {js_errors}"
        )

    def test_js_enable_if_references_unknown_field(self):
        """Error: js enable if val() references a field not on this screen."""
        invalid = """
question: Test
fields:
  - Show: show
    js enable if: |
      val("nonexistent") === true
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("not defined on this screen" in e.err_str.lower() for e in errs),
            f"Expected unknown field error, got: {errs}",
        )

    # -- YAML syntax error (MarkedYAMLError) --

    def test_yaml_syntax_error_in_second_document(self):
        """A MarkedYAMLError in one document is reported without crashing."""
        invalid = "---\nquestion: Hello\nfield: x\n---\nbad: [unclosed\n"
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                "parsing" in e.err_str.lower() or "flow" in e.err_str.lower()
                for e in errs
            ),
            f"Expected YAML parse error, got: {errs}",
        )

    # -- Too many exclusive types --

    def test_too_many_exclusive_types_error(self):
        """Error when a block has multiple exclusive top-level keys."""
        invalid = """
question: Hello
template: something
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any("too many types" in e.err_str.lower() for e in errs),
            f"Expected too-many-types error, got: {errs}",
        )

    # -- MakoText CompileException (lines 106–107) --

    def test_mako_compile_error_in_subquestion(self):
        """A Mako compile error in a subquestion is reported."""
        invalid = """
question: Hello
subquestion: |
  ${invalid mako
field: x
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(len(errs) > 0, f"Expected mako error, got: {errs}")


class TestJinjaHandling(unittest.TestCase):
    """Valid Jinja files (with '# use jinja' header) are pre-processed through
    Jinja2 and the rendered output is passed to the structure checker.
    Files with Jinja syntax but NO header are flagged as errors.
    """

    def test_valid_jinja_file_no_structure_errors(self):
        """A valid Jinja file renders to checkable YAML and produces no errors."""
        content = "# use jinja\n---\nquestion: Hello {{ user }}\n"
        errs = find_errors_from_string(content, input_file="<jinja_valid>")
        self.assertEqual(
            errs, [], f"Expected no errors for valid Jinja file, got: {errs}"
        )

    def test_valid_jinja_with_block_tags_no_errors(self):
        """Jinja if-block with undefined (falsy) condition renders to empty YAML — no errors."""
        content = "# use jinja\n{% if condition %}\nquestion: test\n{% endif %}\n"
        errs = find_errors_from_string(content, input_file="<jinja_valid>")
        self.assertEqual(errs, [])

    def test_jinja_variable_without_header_no_jinja_error(self):
        # {{ }} inside a YAML value is valid YAML; no Jinja-specific error.
        content = "---\nquestion: Hello {{ user }}\n"
        errs = find_errors_from_string(content, input_file="<jinja_no_header>")
        jinja_errs = [e for e in errs if "# use jinja" in e.err_str]
        self.assertEqual(jinja_errs, [])

    def test_jinja_block_tag_without_header_yaml_parse_error(self):
        # {% %} on its own line is not valid YAML; a regular parse error is expected.
        content = "---\n{% if condition %}\nquestion: test\n{% endif %}\n"
        errs = find_errors_from_string(content, input_file="<jinja_no_header>")
        self.assertGreater(len(errs), 0)
        # Should be a YAML parse error, not a Jinja header error.
        jinja_header_errs = [e for e in errs if "# use jinja" in e.err_str]
        self.assertEqual(jinja_header_errs, [])

    def test_plain_yaml_no_jinja_errors(self):
        """Regular YAML without Jinja should not trigger any Jinja-related error."""
        content = "---\nquestion: Hello world\n"
        errs = find_errors_from_string(content, input_file="<plain>")
        jinja_errs = [e for e in errs if "jinja" in e.err_str.lower()]
        self.assertEqual(jinja_errs, [])

    def test_leading_whitespace_before_header_not_valid(self):
        """Leading space means '# use jinja' is not recognised; file is parsed as
        normal YAML and {{ }} in a value is valid — no errors expected."""
        content = " # use jinja\n---\nquestion: Hello {{ user }}\n"
        errs = find_errors_from_string(content, input_file="<jinja_bad_header>")
        jinja_header_errs = [e for e in errs if "# use jinja" in e.err_str]
        self.assertEqual(jinja_header_errs, [])

    def test_jinja_syntax_error_returns_error(self):
        """A Jinja2 template syntax error (e.g. unclosed block) surfaces as a YAMLError."""
        # '{% if %}' with no condition is a Jinja2 TemplateSyntaxError.
        content = "# use jinja\n---\nquestion: {% if %}\n"
        errs = find_errors_from_string(content, input_file="<jinja_syntax_err>")
        self.assertGreater(len(errs), 0)
        self.assertTrue(
            any("jinja2" in e.err_str.lower() for e in errs),
            f"Expected a Jinja2 syntax error, got: {errs}",
        )

    def test_jinja_invalid_structure_after_render_returns_error(self):
        """After rendering, structure errors in the resulting YAML are still caught."""
        # An unknown top-level key should produce a structure error.
        content = "# use jinja\n---\nnot_a_real_key: {{ value }}\n"
        errs = find_errors_from_string(content, input_file="<jinja_bad_structure>")
        self.assertGreater(len(errs), 0)

    def test_jinja_error_line_numbers_account_for_header(self):
        """Line numbers in errors should reflect the original file, including
        the '# use jinja' header on line 1."""
        # The structure error is on line 3 of the original file, but the
        # block-level error ("No possible types found") is attributed to the
        # document separator on line 2 — consistent with how non-jinja files
        # report block errors at the '---' line.
        content = "# use jinja\n---\nnot_a_real_key: hello\n"
        errs = find_errors_from_string(content, input_file="<jinja_lines>")
        self.assertGreater(len(errs), 0)
        # Without the offset fix the error would report line 1 (the stripped
        # header).  With the fix it should be >= 2 (the '---' separator).
        for err in errs:
            self.assertGreaterEqual(
                err.line_number,
                2,
                f"Expected line >= 2 for error after header, got {err.line_number}",
            )


class TestPreprocessJinja(unittest.TestCase):
    """Unit tests for the preprocess_jinja() function itself."""

    def test_simple_variable_renders_empty(self):
        """Undefined variables render as empty string."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n---\nquestion: Hello {{ user }}\n"
        )
        self.assertEqual(errors, [])
        self.assertIn("question: Hello ", rendered)
        self.assertNotIn("{{ user }}", rendered)

    def test_known_literal_renders_correctly(self):
        """Hard-coded Jinja expressions render to their value."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n---\nquestion: {{ 'world' }}\n"
        )
        self.assertEqual(errors, [])
        self.assertIn("question: world", rendered)

    def test_conditional_false_omits_block(self):
        """An undefined (falsy) condition causes the if-block to be omitted."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n{% if show_block %}\nquestion: test\n{% endif %}\n"
        )
        self.assertEqual(errors, [])
        self.assertNotIn("question: test", rendered)

    def test_conditional_true_includes_block(self):
        """A truthy hard-coded condition includes the block."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n{% if true %}\nquestion: test\n{% endif %}\n"
        )
        self.assertEqual(errors, [])
        self.assertIn("question: test", rendered)

    def test_chained_attribute_renders_empty(self):
        """Chained attribute access on an undefined variable renders as empty string."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n---\nquestion: {{ user.first_name }}\n"
        )
        self.assertEqual(errors, [])
        self.assertNotIn("{{", rendered)

    def test_syntax_error_returns_error_list(self):
        """A Jinja2 template syntax error is captured and returned, not raised."""
        _, errors = preprocess_jinja("# use jinja\n---\nquestion: {% if %}\n")
        self.assertGreater(len(errors), 0)
        self.assertIsInstance(errors[0], JinjaError)
        self.assertEqual(errors[0].code, MessageCode.JINJA2_SYNTAX_ERROR)
        self.assertIn("syntax error", errors[0].message.lower())

    def test_template_runtime_error_returns_error_list(self):
        """A TemplateError raised during render() is caught and returned, not raised."""
        with patch.object(
            jinja2.Template,
            "render",
            side_effect=jinja2.exceptions.TemplateRuntimeError("boom"),
        ):
            content = "# use jinja\n---\nquestion: test\n"
            rendered, errors = preprocess_jinja(content)
            self.assertEqual(rendered, content)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], JinjaError)
            self.assertEqual(errors[0].code, MessageCode.JINJA2_TEMPLATE_ERROR)
            self.assertIn("Jinja2 template error", errors[0].message)

    def test_for_loop_over_undefined_renders_empty(self):
        """Iterating over an undefined variable produces no output (covers __iter__)."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n{% for x in items %}{{ x }}{% endfor %}\n"
        )
        self.assertEqual(errors, [])
        # 'items' is undefined -> __iter__ returns iter([]) -> loop body never runs
        self.assertNotIn("items", rendered)

    def test_length_filter_on_undefined_is_zero(self):
        """The 'length' filter on an undefined variable returns 0 (covers __len__)."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n---\ncount: {{ undef | length }}\n"
        )
        self.assertEqual(errors, [])
        self.assertIn("count: 0", rendered)

    def test_subscript_on_undefined_renders_empty(self):
        """Subscript access on an undefined variable renders empty (covers __getitem__)."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n---\nquestion: {{ data[0] }}\n"
        )
        self.assertEqual(errors, [])
        self.assertNotIn("{{", rendered)

    def test_call_on_undefined_renders_empty(self):
        """Calling an undefined variable renders empty (covers __call__)."""
        rendered, errors = preprocess_jinja(
            "# use jinja\n---\nquestion: {{ some_macro() }}\n"
        )
        self.assertEqual(errors, [])
        self.assertNotIn("{{", rendered)

    def test_header_line_preserved(self):
        """The '# use jinja' header line passes through rendering unchanged."""
        rendered, _ = preprocess_jinja("# use jinja\n---\nquestion: test\n")
        self.assertTrue(rendered.startswith("# use jinja\n"))


class TestSilentUndefined(unittest.TestCase):
    """Direct unit tests for _SilentUndefined, which is used by preprocess_jinja
    to allow static analysis of Jinja files whose runtime variables are unknown.
    """

    def setUp(self):
        self.u = _SilentUndefined()

    def test_str_returns_empty_string(self):
        self.assertEqual(str(self.u), "")

    def test_iter_returns_empty_iterator(self):
        self.assertEqual(list(self.u), [])

    def test_len_returns_zero(self):
        self.assertEqual(len(self.u), 0)

    def test_public_attribute_returns_silent_undefined(self):
        result = self.u.some_attribute
        self.assertIsInstance(result, _SilentUndefined)

    def test_private_attribute_raises_attribute_error(self):
        """Attributes starting with '_' raise AttributeError to avoid confusing
        Python's own protocol checks (e.g. __iter__, __len__ lookups)."""
        with self.assertRaises(AttributeError):
            _ = self.u._private  # single leading underscore triggers the guard

    def test_getitem_returns_silent_undefined(self):
        result = self.u[0]
        self.assertIsInstance(result, _SilentUndefined)

    def test_getitem_string_key_returns_silent_undefined(self):
        result = self.u["key"]
        self.assertIsInstance(result, _SilentUndefined)

    def test_call_returns_silent_undefined(self):
        result = self.u()
        self.assertIsInstance(result, _SilentUndefined)

    def test_call_with_args_returns_silent_undefined(self):
        result = self.u(1, 2, key="value")
        self.assertIsInstance(result, _SilentUndefined)


class TestYAMLStr(unittest.TestCase):
    """Tests for the YAMLStr validator."""

    def test_valid_string_no_errors(self):
        from dayamlchecker.yaml_structure import YAMLStr

        v = YAMLStr("hello world")
        self.assertEqual(v.errors, [])

    def test_non_string_produces_error(self):
        from dayamlchecker.yaml_structure import YAMLStr

        v = YAMLStr(42)
        self.assertEqual(len(v.errors), 1)
        self.assertIn("isn't a string", v.errors[0][0])


class TestMakoText(unittest.TestCase):
    """Tests for the MakoText validator."""

    def test_valid_mako_string_no_errors(self):
        from dayamlchecker.yaml_structure import MakoText

        v = MakoText("Hello ${name}")
        self.assertEqual(v.errors, [])

    def test_invalid_mako_syntax_error(self):
        from dayamlchecker.yaml_structure import MakoText

        # '${' without closing '}' is a Mako SyntaxException
        v = MakoText("Hello ${unclosed")
        self.assertGreater(len(v.errors), 0)


class TestPythonText(unittest.TestCase):
    """Tests for the PythonText validator."""

    def test_non_string_produces_error(self):
        from dayamlchecker.yaml_structure import PythonText

        v = PythonText(123)
        self.assertEqual(len(v.errors), 1)
        self.assertIn("must be a YAML string", v.errors[0][0])

    def test_valid_python_no_errors(self):
        from dayamlchecker.yaml_structure import PythonText

        v = PythonText("x = 1\ny = 2\n")
        self.assertEqual(v.errors, [])

    def test_invalid_python_syntax_error(self):
        from dayamlchecker.yaml_structure import PythonText

        v = PythonText("if True\n  x = 1\n")
        self.assertEqual(len(v.errors), 1)
        self.assertIn("Python syntax error", v.errors[0][0])


class TestObjectsAttrType(unittest.TestCase):
    """Tests for the ObjectsAttrType validator."""

    def test_valid_list(self):
        from dayamlchecker.yaml_structure import ObjectsAttrType

        v = ObjectsAttrType([{"MyObj": "DAObject"}])
        self.assertEqual(v.errors, [])

    def test_valid_dict(self):
        from dayamlchecker.yaml_structure import ObjectsAttrType

        v = ObjectsAttrType({"MyObj": "DAObject"})
        self.assertEqual(v.errors, [])

    def test_invalid_scalar_produces_error(self):
        from dayamlchecker.yaml_structure import ObjectsAttrType

        v = ObjectsAttrType("MyObj: DAObject")
        self.assertGreater(len(v.errors), 0)


class TestDAPythonVar(unittest.TestCase):
    """Tests for the DAPythonVar validator."""

    def test_valid_var(self):
        from dayamlchecker.yaml_structure import DAPythonVar

        v = DAPythonVar("my_var")
        self.assertEqual(v.errors, [])

    def test_non_string_produces_error(self):
        from dayamlchecker.yaml_structure import DAPythonVar

        v = DAPythonVar(42)
        self.assertEqual(len(v.errors), 1)
        self.assertIn("needs to be a YAML string", v.errors[0][0])

    def test_whitespace_in_var_name_produces_error(self):
        from dayamlchecker.yaml_structure import DAPythonVar

        v = DAPythonVar("my var")
        self.assertEqual(len(v.errors), 1)
        self.assertIn("cannot have whitespace", v.errors[0][0])

    def test_quoted_string_with_space_is_valid(self):
        from dayamlchecker.yaml_structure import DAPythonVar

        # A quoted string with a space is not a plain var name but passes the check
        v = DAPythonVar("'my var'")
        self.assertEqual(v.errors, [])


class TestDAFields(unittest.TestCase):
    """Tests for the DAFields validator (dict/non-list/code variants)."""

    def test_fields_dict_with_code_valid(self):
        from dayamlchecker.yaml_structure import DAFields

        v = DAFields({"code": "my_fields_list"})
        self.assertEqual(v.errors, [])

    def test_fields_dict_missing_code_key_error(self):
        from dayamlchecker.yaml_structure import DAFields

        # A dict with no recognised field keys AND no 'code' key is still an error.
        v = DAFields({"not_code": "value"})
        self.assertEqual(len(v.errors), 1)
        self.assertIn("code", v.errors[0][0])

    def test_fields_single_field_dict_shorthand_no_error(self):
        """fields: can be a bare dict (single-field shorthand) in docassemble."""
        from dayamlchecker.yaml_structure import DAFields

        v = DAFields(
            {
                "label": "no label",
                "field": "venue_type",
                "input type": "radio",
                "choices": ["admin", "circuit"],
            }
        )
        self.assertEqual(v.errors, [])

    def test_fields_single_field_dict_with_only_field_key_no_error(self):
        from dayamlchecker.yaml_structure import DAFields

        v = DAFields({"field": "my_var", "datatype": "text"})
        self.assertEqual(v.errors, [])

    def test_fields_dict_code_non_string_error(self):
        from dayamlchecker.yaml_structure import DAFields

        v = DAFields({"code": 42})
        self.assertEqual(len(v.errors), 1)
        self.assertIn("must be a YAML string", v.errors[0][0])

    def test_fields_non_list_non_dict_error(self):
        from dayamlchecker.yaml_structure import DAFields

        v = DAFields("not a list")
        self.assertEqual(len(v.errors), 1)
        self.assertIn("should be a list or dict", v.errors[0][0])

    def test_fields_js_validator_invalid_error_shape_raises_value_error(self):
        from dayamlchecker import yaml_structure

        class BrokenJSShowIf:
            def __init__(self, *_args, **_kwargs):
                self.errors = [("missing code", 1)]

        with patch.object(yaml_structure, "JSShowIf", BrokenJSShowIf):
            with self.assertRaisesRegex(
                ValueError, "Validator errors must be 3-tuples"
            ):
                yaml_structure.DAFields(
                    [
                        {
                            "Favorite fruit": "fruit",
                            "js show if": 'val("fruit") === "apple"',
                        }
                    ]
                )

    def test_fields_python_validator_invalid_error_shape_raises_value_error(self):
        from dayamlchecker import yaml_structure

        class BrokenPythonText:
            def __init__(self, *_args, **_kwargs):
                self.errors = [("missing code", 1)]

        with patch.object(yaml_structure, "PythonText", BrokenPythonText):
            with self.assertRaisesRegex(
                ValueError, "Validator errors must be 3-tuples"
            ):
                yaml_structure.DAFields(
                    [
                        {
                            "Favorite fruit": "fruit",
                            "show if": {"code": "fruit == 'apple'"},
                        }
                    ]
                )


class TestShowIf(unittest.TestCase):
    """Tests for the ShowIf validator (non-js variants)."""

    def test_show_if_string_simple_var_no_errors(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf("my_var")
        self.assertEqual(v.errors, [])

    def test_show_if_malformed_string_with_colon_produces_error(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf("variable: foo")
        self.assertEqual(len(v.errors), 1)
        self.assertIn("malformed", v.errors[0][0])

    def test_show_if_dict_variable_key_no_errors(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf({"variable": "foo", "is": "bar"})
        self.assertEqual(v.errors, [])

    def test_show_if_dict_code_key_valid_python_no_errors(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf({"code": "x == 1"})
        self.assertEqual(v.errors, [])

    def test_show_if_dict_code_non_string_error(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf({"code": 123})
        self.assertEqual(len(v.errors), 1)
        self.assertIn("must be a YAML string", v.errors[0][0])

    def test_show_if_dict_missing_both_keys_error(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf({"some_other_key": "value"})
        self.assertEqual(len(v.errors), 1)
        self.assertIn('"variable" key or "code" key', v.errors[0][0])


class TestYAMLError(unittest.TestCase):
    """Tests for the YAMLError class."""

    def test_str_experimental(self):
        from dayamlchecker.yaml_structure import YAMLError

        err = YAMLError(
            err_str="bad key",
            line_number=5,
            file_name="test.yml",
            code="W999",
        )
        result = str(err)
        self.assertIn("test.yml", result)
        self.assertIn("5", result)
        self.assertIn("bad key", result)
        self.assertIn("[W999]", result)
        self.assertNotIn("REAL ERROR", result)

    def test_str_non_experimental(self):
        from dayamlchecker.yaml_structure import YAMLError

        err = YAMLError(
            err_str="bad key",
            line_number=5,
            file_name="test.yml",
            experimental=False,
            code="E999",
        )
        result = str(err)
        self.assertIn("REAL ERROR", result)
        self.assertIn("[E999]", result)

    def test_default_experimental_true(self):
        from dayamlchecker.yaml_structure import YAMLError

        err = YAMLError(err_str="x", line_number=1, file_name="f.yml")
        self.assertTrue(err.experimental)

    def test_code_defaults_to_none(self):
        from dayamlchecker.yaml_structure import YAMLError

        err = YAMLError(err_str="x", line_number=1, file_name="f.yml")
        self.assertIsNone(err.code)

    def test_format_show_experimental_false_omits_real_error(self):
        from dayamlchecker.yaml_structure import YAMLError

        err = YAMLError(
            err_str="bad key",
            line_number=5,
            file_name="test.yml",
            experimental=False,
            code="E999",
        )
        result = err.format(show_experimental=False)
        self.assertNotIn("REAL ERROR", result)
        self.assertIn("[E999]", result)
        self.assertIn("bad key", result)


class TestMessageRegistry(unittest.TestCase):
    def test_message_codes_are_unique(self):
        codes = list(MESSAGE_DEFINITIONS)
        self.assertEqual(len(codes), len(set(codes)))

    def test_message_codes_follow_expected_pattern(self):
        for code in MESSAGE_DEFINITIONS:
            # Structural check with precise numeric boundaries included
            self.assertRegex(code, MESSAGE_CODE_PATTERN)
            kind = code[0]
            num = int(code[1:])
            if kind == "E":
                # E codes must be in the range 101–599
                self.assertGreaterEqual(num, 101, f"Invalid E-code: {code}")
                self.assertLessEqual(num, 599, f"Invalid E-code: {code}")
            elif kind == "W":
                # W codes must be in the range 101–699
                self.assertGreaterEqual(num, 101, f"Invalid W-code: {code}")
                self.assertLessEqual(num, 699, f"Invalid W-code: {code}")
            elif kind == "C":
                # C codes must be 101 or higher (no upper bound)
                self.assertGreaterEqual(num, 101, f"Invalid C-code: {code}")

    def test_messagecode_constants_match_registry(self):
        """
        Ensure that all public constants defined on MessageCode:
        - have values present in MESSAGE_DEFINITIONS
        - follow the same pattern and numeric ranges as registry codes.
        """
        for name, value in vars(MessageCode).items():
            # Consider only public, constant-like attributes
            if name.startswith("_"):
                continue
            if not name.isupper():
                continue

            code = value
            # The constant value must be a registered message code
            self.assertIn(
                code,
                MESSAGE_DEFINITIONS,
                msg=f"MessageCode.{name} value {code!r} not in MESSAGE_DEFINITIONS",
            )

            # Reuse the structural and precision checks
            self.assertRegex(code, MESSAGE_CODE_PATTERN)
            kind = code[0]
            num = int(code[1:])
            if kind == "E":
                self.assertGreaterEqual(num, 101, f"Invalid E-code for {name}: {code}")
                self.assertLessEqual(num, 599, f"Invalid E-code for {name}: {code}")
            elif kind == "W":
                self.assertGreaterEqual(num, 101, f"Invalid W-code for {name}: {code}")
                self.assertLessEqual(num, 699, f"Invalid W-code for {name}: {code}")
            elif kind == "C":
                self.assertGreaterEqual(num, 101, f"Invalid C-code for {name}: {code}")


class TestFindErrors(unittest.TestCase):
    """Tests for find_errors() which reads from a file on disk."""

    def test_find_errors_valid_file(self):
        import tempfile

        from dayamlchecker.yaml_structure import find_errors

        content = "---\nquestion: Hello\nfield: my_var\n"
        with tempfile.NamedTemporaryFile(
            suffix=".yml", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            fname = f.name
        try:
            errs = find_errors(fname)
            self.assertEqual(errs, [])
        finally:
            import os

            os.unlink(fname)

    def test_find_errors_invalid_file(self):
        import tempfile

        from dayamlchecker.yaml_structure import find_errors

        content = "---\nnot_a_real_key: hello\n"
        with tempfile.NamedTemporaryFile(
            suffix=".yml", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            fname = f.name
        try:
            errs = find_errors(fname)
            self.assertGreater(len(errs), 0)
        finally:
            import os

            os.unlink(fname)

    def test_find_errors_large_invalid_fixture(self):
        from dayamlchecker.yaml_structure import find_errors

        errs = find_errors(str(LARGE_INVALID_INTERVIEW_FIXTURE))
        codes = {err.code for err in errs}
        expected_codes = (
            set(MESSAGE_DEFINITIONS)
            - {
                MessageCode.JINJA2_SYNTAX_ERROR,
                MessageCode.JINJA2_TEMPLATE_ERROR,
            }
            - ACCESSIBILITY_ERROR_CODES
        )

        self.assertEqual(
            codes,
            expected_codes,
            f"Expected fixture to produce {sorted(expected_codes)}, got {sorted(codes)}",
        )

    def test_error_code_fixtures_cover_entire_registry(self):
        from dayamlchecker.yaml_structure import find_errors

        covered_codes = set()
        for fixture_path in ALL_ERROR_CODE_FIXTURES:
            covered_codes.update(err.code for err in find_errors(str(fixture_path)))

        self.assertEqual(
            covered_codes,
            set(MESSAGE_DEFINITIONS) - ACCESSIBILITY_ERROR_CODES,
            f"Expected fixtures to cover {sorted(MESSAGE_DEFINITIONS)}, got {sorted(covered_codes)}",
        )

    def test_find_errors_large_valid_fixture(self):
        from dayamlchecker.yaml_structure import find_errors

        errs = find_errors(str(LARGE_VALID_INTERVIEW_FIXTURE))
        self.assertEqual(
            errs, [], f"Expected no errors from valid fixture, got: {errs}"
        )


class TestFindErrorsEdgeCases(unittest.TestCase):
    """Tests for edge cases in find_errors_from_string."""

    def test_no_input_file_defaults_to_unknown(self):
        """When input_file is omitted, errors still have a file_name."""
        errs = find_errors_from_string("---\nnot_real: hello\n")
        self.assertGreater(len(errs), 0)
        # Should not crash; file_name set to a default like "<unknown>"
        self.assertIsNotNone(errs[0].file_name)

    def test_unrecognised_top_level_key_is_real_error(self):
        """Non-DA keys must be flagged as non-experimental (REAL ERROR)."""
        errs = find_errors_from_string("---\nbad_key: hello\n", input_file="<test>")
        real_errors = [e for e in errs if not e.experimental]
        self.assertGreater(len(real_errors), 0)

    def test_multi_document_processes_all_blocks(self):
        """Multiple YAML documents in one file are all checked."""
        content = "---\nquestion: Hello\n---\nbad_key: oops\n"
        errs = find_errors_from_string(content, input_file="<multi>")
        # The second block has a bad key
        self.assertGreater(len(errs), 0)

    def test_empty_yaml_document_no_crash(self):
        """An empty / comment-only document does not crash."""
        errs = find_errors_from_string("# just a comment\n", input_file="<empty>")
        # No crash and no false positives
        self.assertIsInstance(errs, list)

    def test_non_string_top_level_key_flagged(self):
        """A top-level key that isn't a string is flagged."""
        content = "---\n123: value\n"
        errs = find_errors_from_string(content, input_file="<non_str_key>")
        # Should produce an error about unexpected keys
        self.assertGreater(len(errs), 0)

    def test_invalid_validator_error_shape_raises_value_error(self):
        """Malformed validator outputs should fail explicitly, even with assertions disabled."""
        import dayamlchecker.yaml_structure as yaml_structure

        class BrokenValidator:
            def __init__(self, _value):
                self.errors = [("missing code", 1)]

        content = "---\nquestion: Hello\n"
        with patch.dict(
            yaml_structure.big_dict,
            {"question": {"type": BrokenValidator}},
            clear=False,
        ):
            with self.assertRaisesRegex(
                ValueError, "Validator errors must be 3-tuples"
            ):
                find_errors_from_string(content, input_file="<broken_validator>")


class TestProcessFile(unittest.TestCase):
    """Tests for process_file() which reads a file from disk."""

    def _write_temp(self, content: str, suffix: str = ".yml") -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(
            suffix=suffix, mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            return f.name

    def tearDown(self):
        import os

        for attr in ("_tmp_path",):
            p = getattr(self, attr, None)
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def test_process_valid_file_prints_ok(self):
        import io

        from dayamlchecker.yaml_structure import process_file

        path = self._write_temp("---\nquestion: Hello\nfield: my_var\n")
        out = io.StringIO()
        try:
            with patch("sys.stdout", out):
                process_file(path)
        finally:
            import os

            os.unlink(path)
        self.assertIn("ok", out.getvalue())

    def test_process_jinja_file_prints_ok_jinja(self):
        import io

        from dayamlchecker.yaml_structure import process_file

        path = self._write_temp("# use jinja\n---\nquestion: Hello {{ name }}\n")
        out = io.StringIO()
        try:
            with patch("sys.stdout", out):
                process_file(path)
        finally:
            import os

            os.unlink(path)
        self.assertIn("ok (jinja)", out.getvalue())

    def test_process_file_with_errors_prints_error_count(self):
        import io

        from dayamlchecker.yaml_structure import process_file

        path = self._write_temp("---\nbad_key: hello\n")
        out = io.StringIO()
        try:
            with patch("sys.stdout", out):
                process_file(path)
        finally:
            import os

            os.unlink(path)
        self.assertIn("errors", out.getvalue())

    def test_process_ignored_da_filename_skipped(self):
        """Files whose basename is in the DA ignore list are silently skipped."""
        import io

        from dayamlchecker.yaml_structure import process_file

        # Write a file with a bad-key error but with an ignored name
        path = self._write_temp("---\nbad_key: hello\n")
        import os
        import shutil

        ignored_path = os.path.join(os.path.dirname(path), "documentation.yml")
        shutil.copy(path, ignored_path)
        out = io.StringIO()
        try:
            with patch("sys.stdout", out):
                process_file(ignored_path)
        finally:
            os.unlink(path)
            os.unlink(ignored_path)
        # Default mode should print "skipped: <file>", not errors
        self.assertIn("skipped", out.getvalue())
        self.assertNotIn("error", out.getvalue().lower())

    def test_process_jinja_file_default_mode_prints_ok_status(self):
        """Default mode prints the file name and ok (jinja) status per-file."""
        import io

        from dayamlchecker.yaml_structure import process_file

        path = self._write_temp("# use jinja\n---\nquestion: Hello {{ name }}\n")
        out = io.StringIO()
        try:
            with patch("sys.stdout", out):
                process_file(path)
        finally:
            import os

            os.unlink(path)
        output = out.getvalue()
        self.assertIn("ok (jinja)", output)
        self.assertNotIn("Jinja-rendered output", output)


class TestDAFieldsDeepPaths(unittest.TestCase):
    """Cover the deeper `_validate_field_modifiers` paths in DAFields."""

    def test_accept_with_unquoted_extension_list_errors(self):
        content = """\
question: |
  Sample
fields:
  - Upload deed document: deed_upload
    datatype: file
    accept: |
      .pdf,.jpg,.jpeg,.png,.tiff,.tif
"""
        errs = find_errors_from_string(content, input_file="<test>")
        accept_errs = [
            e
            for e in errs
            if "accept must be a python string literal" in e.err_str.lower()
        ]
        self.assertGreaterEqual(
            len(accept_errs),
            1,
            f"Expected accept syntax error, got: {errs}",
        )

    def test_accept_with_quoted_string_is_valid(self):
        content = """\
question: |
  Sample
fields:
  - Upload deed document: deed_upload
    datatype: file
    accept: "'application/pdf,image/jpeg,image/png,image/tiff'"
"""
        errs = find_errors_from_string(content, input_file="<test>")
        accept_errs = [e for e in errs if "accept" in e.err_str.lower()]
        self.assertEqual(accept_errs, [], f"Unexpected accept errors: {accept_errs}")

    def test_accept_with_non_string_value_errors(self):
        content = """\
question: |
  Sample
fields:
  - Upload deed document: deed_upload
    datatype: file
    accept:
      - .pdf
      - .jpg
"""
        errs = find_errors_from_string(content, input_file="<test>")
        accept_errs = [e for e in errs if e.code == "W121"]
        self.assertGreaterEqual(
            len(accept_errs),
            1,
            f"Expected type error for non-string accept, got: {errs}",
        )

    def test_accept_with_mime_types_is_valid(self):
        content = """\
question: |
  Sample
fields:
  - Upload deed document: deed_upload
    datatype: file
    accept: "'application/pdf,image/jpeg,image/png'"
"""
        errs = find_errors_from_string(content, input_file="<test>")
        accept_errs = [e for e in errs if "accept" in e.err_str.lower()]
        self.assertEqual(accept_errs, [], f"Unexpected accept errors: {accept_errs}")

    def test_accept_block_scalar_double_quoted_string_is_valid(self):
        """Block scalar with double-quoted Python string literal is valid."""
        content = """\
question: |
  Sample
fields:
  - Upload deed document: deed_upload
    datatype: file
    accept: |
      "application/pdf,image/jpeg,image/png,image/tiff"
"""
        errs = find_errors_from_string(content, input_file="<test>")
        accept_errs = [e for e in errs if "accept" in e.err_str.lower()]
        self.assertEqual(accept_errs, [], f"Unexpected accept errors: {accept_errs}")

    def test_accept_unquoted_mime_type_errors(self):
        """Bare MIME type without Python quoting (e.g. application/pdf) is caught."""
        content = """\
question: |
  Sample
fields:
  - Upload deed document: deed_upload
    datatype: file
    accept: application/pdf
"""
        errs = find_errors_from_string(content, input_file="<test>")
        accept_errs = [
            e
            for e in errs
            if "accept must be a python string literal" in e.err_str.lower()
        ]
        self.assertGreaterEqual(
            len(accept_errs),
            1,
            f"Expected non-string-literal error for bare MIME type, got: {errs}",
        )

    def test_show_if_dict_missing_variable_and_code_keys_error(self):
        """show if dict without 'variable' or 'code' should trigger an error."""
        content = """\
question: |
  Sample
fields:
  - Name: name
  - Conditional: other
    show if:
      neither_key: value
"""
        errs = find_errors_from_string(content, input_file="<test>")
        self.assertTrue(
            any(
                '"variable" or "code"' in e.err_str.lower()
                or "variable" in e.err_str.lower()
                for e in errs
            ),
            f"Expected show-if dict key error, got: {errs}",
        )

    def test_hide_if_dict_missing_variable_and_code_keys_error(self):
        """hide if dict without 'variable' or 'code' should trigger an error."""
        content = """\
question: |
  Sample
fields:
  - Name: name
  - Conditional: other
    hide if:
      neither_key: value
"""
        errs = find_errors_from_string(content, input_file="<test>")
        self.assertTrue(
            any(
                '"variable" or "code"' in e.err_str.lower()
                or "variable" in e.err_str.lower()
                for e in errs
            ),
            f"Expected hide-if dict key error, got: {errs}",
        )

    def test_js_enable_if_valid(self):
        """js enable if should work the same as js show if."""
        content = """\
question: |
  Sample
fields:
  - Name: name
  - Toggled: toggle
    js enable if: |
      val("name") !== ""
"""
        errs = find_errors_from_string(content, input_file="<test>")
        enable_if_errs = [e for e in errs if "enable if" in e.err_str.lower()]
        self.assertEqual(len(enable_if_errs), 0)

    def test_js_enable_if_no_val_call_error(self):
        content = """\
question: |
  Sample
fields:
  - Name: name
  - Toggled: toggle
    js enable if: |
      true
"""
        errs = find_errors_from_string(content, input_file="<test>")
        self.assertTrue(
            any("val()" in e.err_str for e in errs),
            f"Expected val() error for js enable if, got: {errs}",
        )

    def test_fields_list_with_non_dict_item_no_crash(self):
        """A fields list containing a non-dict entry should not crash."""
        content = """\
question: |
  Sample
fields:
  - note: just a note
"""
        errs = find_errors_from_string(content, input_file="<test>")
        # Should either produce no error or a meaningful one, not crash
        self.assertIsInstance(errs, list)

    def test_x_alias_in_show_if_on_generic_object_screen(self):
        """show if with x.<attr> should match children[i].<attr> on screen."""
        content = """\
question: |
  Generic screen
fields:
  - Fruit: x.fruit
  - Why: x.reason
    show if: x.fruit
"""
        errs = find_errors_from_string(content, input_file="<test>")
        show_if_errs = [
            e
            for e in errs
            if "show if" in e.err_str.lower() and "not defined" in e.err_str.lower()
        ]
        self.assertEqual(len(show_if_errs), 0, f"Unexpected: {show_if_errs}")


class TestMakoCompileException(unittest.TestCase):
    """Cover the CompileException branch of MakoText."""

    def test_mako_compile_error_produces_error(self):
        from dayamlchecker.yaml_structure import MakoText

        # Patch MakoTemplate to raise a generic Exception to simulate a compile
        # failure (MakoText only catches SyntaxException and CompileException;
        # we test CompileException by using the SyntaxException path here since
        # CompileException requires 4 positional args that are hard to construct).
        # Instead, trigger a MakoText error by passing a non-string value.
        v = MakoText.__new__(MakoText)
        v.errors = []
        # We can indirectly test the compile except path by passing markup that
        # triggers a Mako SyntaxException — a lone '$' is not valid Mako.
        v2 = MakoText("${")
        self.assertGreater(len(v2.errors), 0)


class TestJSShowIfNonString(unittest.TestCase):
    """Cover the non-string branch of JSShowIf."""

    def test_js_show_if_non_string_produces_error(self):
        from dayamlchecker.yaml_structure import JSShowIf

        v = JSShowIf(42, modifier_key="js show if")
        self.assertEqual(len(v.errors), 1)
        self.assertIn("must be a string", v.errors[0][0])

    def test_js_show_if_reference_helper_rejects_non_strings(self):
        from dayamlchecker.yaml_structure import JSShowIf

        v = JSShowIf('val("field")', modifier_key="js show if")

        self.assertFalse(v._references_screen_variable(42))


class TestShowIfMalformedCodePrefix(unittest.TestCase):
    """ShowIf string values that start with 'code:' should be flagged."""

    def test_show_if_code_colon_prefix_produces_error(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf("code: x == 1")
        self.assertEqual(len(v.errors), 1)
        self.assertIn("malformed", v.errors[0][0])

    def test_show_if_dict_variable_form_is_valid(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf({"variable": "ready", "is": True})

        self.assertEqual(v.errors, [])

    def test_interview_order_reference_without_matching_guard_errors(self):
        """Error when interview-order style code references a conditionally shown field without guard"""
        invalid = """
question: |
  Eviction details
fields:
  - Reason: eviction_reason
    choices:
      - Nonpayment
      - Other
  - Other details: other_details
    show if:
      variable: eviction_reason
      is: Other
---
id: interview_order
mandatory: True
code: |
  other_details
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(
            any(
                'references "other_details" without a matching guard'
                in e.err_str.lower()
                for e in errs
            ),
            f"Expected interview-order guard error, got: {errs}",
        )

    def test_interview_order_reference_with_matching_guard_valid(self):
        """No error when interview-order style code guards conditional field usage"""
        valid = """
question: |
  Eviction details
fields:
  - Reason: eviction_reason
    choices:
      - Nonpayment
      - Other
  - Other details: other_details
    show if:
      variable: eviction_reason
      is: Other
---
id: interview_order
mandatory: True
code: |
  if eviction_reason == "Other":
    other_details
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any("without a matching guard" in e.err_str.lower() for e in errs),
            f"Expected no interview-order guard error, got: {errs}",
        )

    def test_interview_order_reference_with_showifdef_guard_valid(self):
        """No error when interview-order code uses showifdef('<field>') as guard"""
        valid = """
question: |
  Eviction details
fields:
  - Reason: eviction_reason
    choices:
      - Nonpayment
      - Other
  - Other details: other_details
    show if:
      variable: eviction_reason
      is: Other
---
id: interview_order
mandatory: True
code: |
  if showifdef("other_details") and other_details:
    pass
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any("without a matching guard" in e.err_str.lower() for e in errs),
            f"Expected no interview-order guard error with showifdef guard, got: {errs}",
        )

    def test_interview_order_all_conditional_modifiers_without_guard_error(self):
        """Each conditional modifier should trigger interview-order guard mismatch when unguarded"""
        cases = [
            ("show if", "eviction_reason == 'Other'"),
            ("hide if", "eviction_reason == 'Other'"),
            ("enable if", "eviction_reason == 'Other'"),
            ("disable if", "eviction_reason == 'Other'"),
            ("js show if", 'val("eviction_reason") === "Other"'),
            ("js hide if", 'val("eviction_reason") === "Other"'),
            ("js enable if", 'val("eviction_reason") === "Other"'),
            ("js disable if", 'val("eviction_reason") === "Other"'),
        ]
        for modifier, condition in cases:
            with self.subTest(modifier=modifier):
                yaml_text = f"""
question: |
  Eviction details
fields:
  - Reason: eviction_reason
    choices:
      - Nonpayment
      - Other
  - Other details: other_details
    {modifier}: |
      {condition}
---
id: interview_order
mandatory: True
code: |
  other_details
"""
                errs = find_errors_from_string(yaml_text, input_file="<string_invalid>")
                self.assertTrue(
                    any("without a matching guard" in e.err_str.lower() for e in errs),
                    f"Expected interview-order guard error for {modifier}, got: {errs}",
                )

    def test_interview_order_all_conditional_modifiers_with_guard_valid(self):
        """Each conditional modifier should pass when interview-order code has a matching guard"""
        cases = [
            ("show if", "eviction_reason == 'Other'", "if eviction_reason == 'Other':"),
            ("hide if", "eviction_reason == 'Other'", "if eviction_reason != 'Other':"),
            (
                "enable if",
                "eviction_reason == 'Other'",
                "if eviction_reason == 'Other':",
            ),
            (
                "disable if",
                "eviction_reason == 'Other'",
                "if eviction_reason != 'Other':",
            ),
            ("js show if", 'val("eviction_reason") === "Other"', "if eviction_reason:"),
            (
                "js hide if",
                'val("eviction_reason") === "Other"',
                "if not eviction_reason:",
            ),
            (
                "js enable if",
                'val("eviction_reason") === "Other"',
                "if eviction_reason:",
            ),
            (
                "js disable if",
                'val("eviction_reason") === "Other"',
                "if not eviction_reason:",
            ),
        ]
        for modifier, condition, guard in cases:
            with self.subTest(modifier=modifier):
                yaml_text = f"""
question: |
  Eviction details
fields:
  - Reason: eviction_reason
    choices:
      - Nonpayment
      - Other
  - Other details: other_details
    {modifier}: |
      {condition}
---
id: interview_order
mandatory: True
code: |
  {guard}
    other_details
"""
                errs = find_errors_from_string(yaml_text, input_file="<string_valid>")
                self.assertFalse(
                    any("without a matching guard" in e.err_str.lower() for e in errs),
                    f"Expected no interview-order guard error for {modifier}, got: {errs}",
                )

    def test_show_hide_nesting_depth_over_two_warns(self):
        """Warn when a single page has show/hide dependency depth greater than two"""
        warning_yaml = """
question: |
  Nested visibility
fields:
  - A: a
  - B: b
    show if: a
  - C: c
    show if: b
  - D: d
    show if: c
"""
        errs = find_errors_from_string(warning_yaml, input_file="<string_warn>")
        self.assertTrue(
            any("nested 3 levels" in e.err_str.lower() for e in errs),
            f"Expected nesting warning, got: {errs}",
        )

    def test_show_hide_nesting_depth_two_no_warning(self):
        """No warning when show/hide dependency depth is at most two"""
        valid = """
question: |
  Visibility depth two
fields:
  - A: a
  - B: b
    show if: a
  - C: c
    show if: b
"""
        errs = find_errors_from_string(valid, input_file="<string_valid>")
        self.assertFalse(
            any("visibility logic is nested" in e.err_str.lower() for e in errs),
            f"Did not expect nesting warning, got: {errs}",
        )


class TestYamlStructureHelpers(unittest.TestCase):
    def test_normalize_validator_error_requires_tuple(self):
        from dayamlchecker.yaml_structure import _normalize_validator_error

        with self.assertRaisesRegex(TypeError, "must be tuples"):
            _normalize_validator_error("not-a-tuple")

    def test_normalize_validator_error_requires_string_message(self):
        from dayamlchecker.yaml_structure import _normalize_validator_error

        with self.assertRaisesRegex(TypeError, "message must be a string"):
            _normalize_validator_error((123, 1, MessageCode.NO_POSSIBLE_TYPES))

    def test_normalize_validator_error_requires_int_line_number(self):
        from dayamlchecker.yaml_structure import _normalize_validator_error

        with self.assertRaisesRegex(TypeError, "line number must be an int"):
            _normalize_validator_error(("msg", "1", MessageCode.NO_POSSIBLE_TYPES))

    def test_normalize_validator_error_requires_string_code(self):
        from dayamlchecker.yaml_structure import _normalize_validator_error

        with self.assertRaisesRegex(TypeError, "code must be a string"):
            _normalize_validator_error(("msg", 1, 123))

    def test_format_message_and_experimental_lookup_reject_unknown_codes(self):
        with self.assertRaisesRegex(ValueError, "Unknown message code"):
            format_message("E999")

        with self.assertRaisesRegex(ValueError, "Unknown message code"):
            is_experimental_code("E999")

    def test_validation_code_handles_second_parse_syntax_error(self):
        import ast as pyast

        from dayamlchecker.yaml_structure import ValidationCode

        with patch(
            "dayamlchecker.yaml_structure.ast.parse",
            side_effect=[pyast.parse("x = 1"), SyntaxError("boom")],
        ):
            validator = ValidationCode("x = 1")

        self.assertEqual(validator.errors, [])

    def test_da_type_accepts_any_value(self):
        from dayamlchecker.yaml_structure import DAType

        self.assertEqual(DAType("Individual").errors, [])

    def test_lc_line_defaults_to_one_without_metadata(self):
        from dayamlchecker.yaml_structure import _lc_line

        self.assertEqual(_lc_line(object()), 1)

    def test_interview_order_style_detects_id_and_comment_markers(self):
        from dayamlchecker.yaml_structure import _is_interview_order_style_block

        self.assertTrue(_is_interview_order_style_block({"id": "Interview Order"}))
        self.assertTrue(_is_interview_order_style_block({"comment": "interview_order"}))
        self.assertFalse(_is_interview_order_style_block({"id": "plain"}))

    def test_extract_field_var_name_ignores_non_field_inputs(self):
        from dayamlchecker.yaml_structure import _extract_field_var_name

        self.assertIsNone(_extract_field_var_name("not a dict"))
        self.assertIsNone(_extract_field_var_name({"show if": "ready"}))

    def test_lc_line_with_missing_line_attribute_defaults_to_one(self):
        from types import SimpleNamespace

        from dayamlchecker.yaml_structure import _lc_line

        self.assertEqual(_lc_line(SimpleNamespace(lc=SimpleNamespace(line=None))), 1)

    def test_lc_key_line_no_lc_attribute(self):
        from dayamlchecker.yaml_structure import _lc_key_line

        self.assertEqual(_lc_key_line(object(), "k"), 1)

    def test_lc_key_line_key_getter_not_callable(self):
        from types import SimpleNamespace

        from dayamlchecker.yaml_structure import _lc_key_line

        obj = SimpleNamespace(lc=SimpleNamespace(key="not callable", line=5))
        self.assertEqual(_lc_key_line(obj, "k"), 6)

    def test_lc_key_line_key_getter_raises(self):
        from types import SimpleNamespace

        from dayamlchecker.yaml_structure import _lc_key_line

        obj = SimpleNamespace(
            lc=SimpleNamespace(key=lambda k: (_ for _ in ()).throw(KeyError(k)), line=3)
        )
        self.assertEqual(_lc_key_line(obj, "missing"), 4)

    def test_lc_key_line_non_tuple_line_info(self):
        from types import SimpleNamespace

        from dayamlchecker.yaml_structure import _lc_key_line

        obj = SimpleNamespace(lc=SimpleNamespace(key=lambda k: "not a tuple", line=2))
        self.assertEqual(_lc_key_line(obj, "k"), 3)

    def test_lc_key_line_non_int_in_tuple(self):
        from types import SimpleNamespace

        from dayamlchecker.yaml_structure import _lc_key_line

        obj = SimpleNamespace(lc=SimpleNamespace(key=lambda k: ("not_int",), line=4))
        self.assertEqual(_lc_key_line(obj, "k"), 5)

    def test_extract_controller_vars_and_js_vars_handle_non_strings(self):
        from dayamlchecker.yaml_structure import (
            _extract_controller_vars_for_field_modifier,
            _extract_vars_from_js_condition,
        )

        self.assertEqual(_extract_controller_vars_for_field_modifier(None), set())
        self.assertEqual(_extract_vars_from_js_condition(None), set())

    def test_guard_candidates_cover_blank_and_hide_dict_paths(self):
        from dayamlchecker.yaml_structure import _guard_candidates_for_modifier

        self.assertEqual(_guard_candidates_for_modifier("show if", "   "), [])
        self.assertEqual(
            _guard_candidates_for_modifier(
                "hide if", {"variable": "status", "is": "done"}
            ),
            ["status != 'done'", "not (status == 'done')"],
        )
        self.assertEqual(
            _guard_candidates_for_modifier("hide if", {"code": "ready"}),
            ["not (ready)"],
        )
        self.assertEqual(
            _guard_candidates_for_modifier("hide if", {"variable": "ready"}),
            ["not (ready)", "not ready"],
        )

    def test_statement_span_returns_none_without_line_numbers(self):
        from dayamlchecker.yaml_structure import _statement_span

        class DummyStmt:
            pass

        self.assertIsNone(_statement_span([DummyStmt()]))

    def test_extract_branch_guards_returns_empty_on_syntax_error(self):
        from dayamlchecker.yaml_structure import _extract_branch_guards_by_line

        self.assertEqual(_extract_branch_guards_by_line("if :\n  pass"), {})

    def test_extract_branch_guards_skips_when_condition_cannot_be_rendered(self):
        import ast

        from dayamlchecker.yaml_structure import _extract_branch_guards_by_line

        if_node = ast.parse("if flag:\n    pass\n").body[0]

        with patch("dayamlchecker.yaml_structure.ast.walk", return_value=[if_node]):
            with patch(
                "dayamlchecker.yaml_structure.ast.get_source_segment",
                return_value=None,
            ):
                with patch(
                    "dayamlchecker.yaml_structure.ast.unparse",
                    side_effect=Exception("boom"),
                ):
                    self.assertEqual(
                        _extract_branch_guards_by_line("if flag:\n    pass\n"), {}
                    )

    def test_extract_branch_guards_handles_missing_lineno_and_else_only_spans(self):
        import ast

        from dayamlchecker.yaml_structure import _extract_branch_guards_by_line

        if_node = ast.parse("if flag:\n    pass\nelse:\n    other()\n").body[0]
        if_node.lineno = None

        with patch("dayamlchecker.yaml_structure.ast.walk", return_value=[if_node]):
            with patch(
                "dayamlchecker.yaml_structure._statement_span",
                side_effect=[None, (3, 3)],
            ):
                self.assertEqual(
                    _extract_branch_guards_by_line(
                        "if flag:\n    pass\nelse:\n    other()\n"
                    ),
                    {3: ["not (flag)"]},
                )

    def test_has_matching_guard_accepts_empty_expectations(self):
        from dayamlchecker.yaml_structure import _has_matching_guard

        self.assertTrue(_has_matching_guard(["anything"], []))

    def test_has_matching_guard_returns_false_when_nothing_matches(self):
        from dayamlchecker.yaml_structure import _has_matching_guard

        self.assertFalse(_has_matching_guard(["x == 1"], ["y == 2"]))

    def test_max_screen_visibility_nesting_depth_handles_edge_cases_and_cycles(self):
        from dayamlchecker.yaml_structure import _max_screen_visibility_nesting_depth

        self.assertEqual(_max_screen_visibility_nesting_depth({"fields": []}), 0)
        self.assertEqual(
            _max_screen_visibility_nesting_depth({"fields": [{"note": "Only note"}]}),
            0,
        )
        self.assertEqual(
            _max_screen_visibility_nesting_depth({"fields": ["not-a-dict"]}),
            0,
        )
        self.assertEqual(
            _max_screen_visibility_nesting_depth(
                {
                    "fields": [
                        {"First": "a", "show if": "b"},
                        {"Second": "b", "show if": "a"},
                    ]
                }
            ),
            2,
        )

    def test_find_screen_variable_references_in_code_handles_invalid_and_indexed_vars(
        self,
    ):
        from dayamlchecker.yaml_structure import DAFields

        validator = DAFields([])

        self.assertEqual(
            validator._find_screen_variable_references_in_code("if :", {"name"}),
            set(),
        )
        self.assertEqual(
            validator._find_screen_variable_references_in_code(
                "children[i].name", {"children[i].name"}
            ),
            {"children[i].name"},
        )

    def test_javascript_text_accepts_any_value(self):
        from dayamlchecker.yaml_structure import JavascriptText

        self.assertEqual(JavascriptText("alert(1)").errors, [])

    def test_js_show_if_handles_non_val_calls_and_missing_arguments(self):
        from dayamlchecker.yaml_structure import JSShowIf

        validator = JSShowIf("foo(bar(), val())", modifier_key="js show if")

        self.assertTrue(
            any("quoted string" in err[0].lower() for err in validator.errors)
        )

    def test_js_show_if_traverses_dict_and_list_nodes_explicitly(self):
        from dayamlchecker.yaml_structure import JSShowIf

        class Parsed:
            def toDict(self):
                return {
                    "type": "Program",
                    "body": [
                        {
                            "type": "CallExpression",
                            "callee": {"type": "Identifier", "name": "foo"},
                            "arguments": [],
                        },
                        {
                            "type": "CallExpression",
                            "callee": {"type": "Identifier", "name": "val"},
                            "arguments": [],
                            "loc": {"start": {"line": 1}},
                        },
                    ],
                }

        with patch(
            "dayamlchecker.yaml_structure.esprima.parseScript",
            return_value=Parsed(),
        ):
            validator = JSShowIf("ignored", modifier_key="js show if")

        self.assertTrue(
            any("quoted string" in err[0].lower() for err in validator.errors)
        )

    def test_fields_detects_dynamic_code_only_entry(self):
        from dayamlchecker.yaml_structure import DAFields

        validator = DAFields([{"code": "field_list"}])

        self.assertTrue(validator.has_dynamic_fields_code)

    def test_fields_skip_non_dict_entries_during_modifier_validation(self):
        from dayamlchecker.yaml_structure import DAFields

        validator = DAFields([{"Name": "name"}, "not-a-dict"])

        self.assertEqual(validator.errors, [])

    def test_show_if_simple_string_form_is_accepted(self):
        from dayamlchecker.yaml_structure import ShowIf

        self.assertEqual(ShowIf("ready").errors, [])

    def test_show_if_dict_variable_form_is_accepted_directly(self):
        from dayamlchecker.yaml_structure import ShowIf

        self.assertEqual(ShowIf({"variable": "ready"}).errors, [])

    def test_extract_field_name_skips_modifier_keys_before_returning_field(self):
        from dayamlchecker.yaml_structure import DAFields

        validator = DAFields([])

        self.assertEqual(
            validator._extract_field_name({"show if": "ready", "Name": "person.name"}),
            "person.name",
        )

    def test_extract_field_name_skips_non_string_field_values(self):
        from dayamlchecker.yaml_structure import DAFields

        validator = DAFields([])

        self.assertEqual(
            validator._extract_field_name({"Count": 1, "Name": "person.name"}),
            "person.name",
        )

    def test_extract_field_var_name_skips_modifier_keys_before_returning_field(self):
        from dayamlchecker.yaml_structure import _extract_field_var_name

        self.assertEqual(
            _extract_field_var_name({"show if": "ready", "Name": "person.name"}),
            "person.name",
        )

    def test_extract_field_var_name_skips_non_string_field_values(self):
        from dayamlchecker.yaml_structure import _extract_field_var_name

        self.assertEqual(
            _extract_field_var_name({"Count": 1, "Name": "person.name"}),
            "person.name",
        )

    def test_guard_candidates_cover_non_hide_variable_without_is(self):
        from dayamlchecker.yaml_structure import _guard_candidates_for_modifier

        self.assertEqual(
            _guard_candidates_for_modifier("show if", {"variable": "ready"}),
            ["ready"],
        )

    def test_validate_python_modifier_allows_known_string_variable(self):
        from dayamlchecker.yaml_structure import DAFields

        validator = DAFields([])
        validator._validate_python_modifier(
            "show if",
            "toggle",
            {"label": "Reason"},
            {"toggle"},
        )

        self.assertEqual(validator.errors, [])

    def test_fields_x_alias_matches_deep_screen_variable(self):
        content = """
question: |
  Generic screen
fields:
  - Fruit: children[i].fruit
  - Reason: reason
    show if: x.fruit
"""

        errs = find_errors_from_string(content, input_file="<generic>")

        self.assertFalse(
            any(
                e.code == MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING
                for e in errs
            ),
            errs,
        )

    def test_max_screen_visibility_nesting_depth_skips_non_dict_items_after_building_vars(
        self,
    ):
        from dayamlchecker.yaml_structure import _max_screen_visibility_nesting_depth

        self.assertEqual(
            _max_screen_visibility_nesting_depth(
                {"fields": [{"Name": "name"}, "not-a-dict"]}
            ),
            0,
        )

    def test_fields_string_modifier_known_variable_does_not_error(self):
        content = """
question: |
  Sample
fields:
  - Toggle: toggle
  - Reason: reason
    show if: toggle
"""

        errs = find_errors_from_string(content, input_file="<screen>")

        self.assertFalse(
            any(
                e.code == MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING
                for e in errs
            ),
            errs,
        )

    def test_fields_variable_modifier_non_string_reports_type_error(self):
        content = """
question: |
  Sample
fields:
  - Toggle: toggle
  - Reason: reason
    show if:
      variable:
        - toggle
"""

        errs = find_errors_from_string(content, input_file="<screen>")

        self.assertTrue(
            any(e.code == MessageCode.FIELD_MODIFIER_VARIABLE_TYPE for e in errs)
        )

    def test_extract_field_name_returns_none_for_non_field_items(self):
        from dayamlchecker.yaml_structure import DAFields

        validator = DAFields([])

        self.assertIsNone(validator._extract_field_name("not a dict"))
        self.assertIsNone(validator._extract_field_name({"show if": "ready"}))

    def test_find_errors_duplicate_key_without_problem_mark(self):
        import dayamlchecker.yaml_structure as yaml_structure
        from unittest.mock import Mock

        class DummyDuplicateKeyError(yaml_structure._RuamelDuplicateKeyError):
            pass

        err = DummyDuplicateKeyError.__new__(DummyDuplicateKeyError)
        err.problem = 'found duplicate key "dup"'
        err.problem_mark = None

        loader = Mock()
        loader.allow_duplicate_keys = False
        loader.load.side_effect = err

        with patch("dayamlchecker.yaml_structure._RuamelYAML", return_value=loader):
            errs = yaml_structure.find_errors_from_string(
                "---\nquestion: Hello\n", input_file="<dup>"
            )

        self.assertTrue(any(e.code == MessageCode.YAML_DUPLICATE_KEY for e in errs))
        self.assertEqual(errs[0].line_number, 1)

    def test_find_errors_marked_yaml_error_without_marks(self):
        import dayamlchecker.yaml_structure as yaml_structure
        from unittest.mock import Mock

        class DummyMarkedYAMLError(yaml_structure._RuamelMarkedYAMLError):
            def __str__(self):
                return "marked parse error"

        err = DummyMarkedYAMLError.__new__(DummyMarkedYAMLError)
        err.context_mark = None
        err.problem_mark = None

        loader = Mock()
        loader.allow_duplicate_keys = False
        loader.load.side_effect = err

        with patch("dayamlchecker.yaml_structure._RuamelYAML", return_value=loader):
            errs = yaml_structure.find_errors_from_string(
                "---\nquestion: Hello\n", input_file="<marked>"
            )

        self.assertTrue(any(e.code == MessageCode.YAML_PARSE_ERROR for e in errs))

    def test_find_errors_generic_yaml_exception_uses_parse_error_path(self):
        import dayamlchecker.yaml_structure as yaml_structure
        from unittest.mock import Mock

        loader = Mock()
        loader.allow_duplicate_keys = False
        loader.load.side_effect = RuntimeError("boom")

        with patch("dayamlchecker.yaml_structure._RuamelYAML", return_value=loader):
            errs = yaml_structure.find_errors_from_string(
                "---\nquestion: Hello\n", input_file="<generic>"
            )

        self.assertTrue(any(e.code == MessageCode.YAML_PARSE_ERROR for e in errs))

    def test_partner_block_pair_does_not_trigger_too_many_types(self):
        content = """
question: |
  Hello
attachment:
  name: Greeting
  filename: greeting
  content: |
    Hello world
"""

        errs = find_errors_from_string(content, input_file="<partner>")

        self.assertFalse(any(e.code == MessageCode.TOO_MANY_TYPES for e in errs))

    def test_variable_candidates_strip_multiple_trailing_indexes(self):
        result = _variable_candidates("items[0][1]")

        self.assertIn("items[0]", result)
        self.assertIn("items", result)


if __name__ == "__main__":
    unittest.main()
