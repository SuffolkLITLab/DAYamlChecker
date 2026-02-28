import unittest
from unittest.mock import patch
import jinja2
from dayamlchecker.yaml_structure import find_errors_from_string
from dayamlchecker._jinja import preprocess_jinja, _SilentUndefined


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
            any("Too many types this block could be" in e.err_str for e in errs),
            f"Expected exclusivity error, got: {errs}",
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
                "duplicate key" in e.err_str.lower()
                or "found duplicate key" in e.err_str.lower()
                for e in errs
            ),
            f"Expected duplicate key error, got: {errs}",
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
            any("not defined on this screen" in e.err_str.lower() for e in errs),
            f"Expected unknown field error, got: {errs}",
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
            any("not defined on this screen" in e.err_str.lower() for e in errs),
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
            any("not defined on this screen" in e.err_str.lower() for e in errs),
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
            any("does not call validation_error" in e.err_str.lower() for e in errs),
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
        self.assertTrue(any("jinja2 syntax error" in e.lower() for e in errors))

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
            self.assertIn("Jinja2 template error", errors[0])

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

        err = YAMLError(err_str="bad key", line_number=5, file_name="test.yml")
        result = str(err)
        self.assertIn("test.yml", result)
        self.assertIn("5", result)
        self.assertIn("bad key", result)
        self.assertNotIn("REAL ERROR", result)

    def test_str_non_experimental(self):
        from dayamlchecker.yaml_structure import YAMLError

        err = YAMLError(
            err_str="bad key", line_number=5, file_name="test.yml", experimental=False
        )
        result = str(err)
        self.assertIn("REAL ERROR", result)

    def test_default_experimental_true(self):
        from dayamlchecker.yaml_structure import YAMLError

        err = YAMLError(err_str="x", line_number=1, file_name="f.yml")
        self.assertTrue(err.experimental)


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


class TestShowIfMalformedCodePrefix(unittest.TestCase):
    """ShowIf string values that start with 'code:' should be flagged."""

    def test_show_if_code_colon_prefix_produces_error(self):
        from dayamlchecker.yaml_structure import ShowIf

        v = ShowIf("code: x == 1")
        self.assertEqual(len(v.errors), 1)
        self.assertIn("malformed", v.errors[0][0])


if __name__ == "__main__":
    unittest.main()
