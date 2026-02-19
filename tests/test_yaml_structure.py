import unittest
from dayamlchecker.yaml_structure import find_errors_from_string


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
        self.assertTrue(any('Too many types this block could be' in e.err_str for e in errs), f"Expected exclusivity error, got: {errs}")

    def test_duplicate_key_error(self):
        duplicate = """
question: |
  Q1
question: |
  Q2
"""
        errs = find_errors_from_string(duplicate, input_file="<string_dups>")
        self.assertTrue(len(errs) > 0, f"Expected parser error for duplicate keys, got: {errs}")
        self.assertTrue(any('duplicate key' in e.err_str.lower() or 'found duplicate key' in e.err_str.lower() for e in errs), f"Expected duplicate key error, got: {errs}")

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
        js_show_if_errors = [e for e in errs if 'js show if' in e.err_str.lower()]
        self.assertEqual(len(js_show_if_errors), 0, f"Expected no js show if errors, got: {js_show_if_errors}")

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
        self.assertTrue(any('val()' in e.err_str and 'at least one' in e.err_str for e in errs), f"Expected val() requirement error, got: {errs}")

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
        js_show_if_errors = [e for e in errs if 'js show if' in e.err_str.lower() or 'val()' in e.err_str.lower()]
        self.assertEqual(len(js_show_if_errors), 0, f"Expected no js show if errors, got: {js_show_if_errors}")

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
        self.assertTrue(any('quoted string' in e.err_str.lower() for e in errs), f"Expected quoted string error, got: {errs}")

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
        self.assertTrue(any('not defined on this screen' in e.err_str.lower() for e in errs), f"Expected unknown field error, got: {errs}")

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
        self.assertTrue(any('quoted string' in e.err_str.lower() for e in errs), f"Expected quoted string error, got: {errs}")

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
        val_errors = [e for e in errs if 'quoted string' in e.err_str.lower()]
        self.assertEqual(len(val_errors), 0, f"Expected no quoted string errors, got: {val_errors}")

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
        syntax_errors = [e for e in errs if 'invalid javascript' in e.err_str.lower()]
        self.assertEqual(len(syntax_errors), 0, f"Expected no syntax errors with Mako, got: {syntax_errors}")

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
        syntax_errors = [e for e in errs if 'invalid javascript' in e.err_str.lower()]
        self.assertGreater(len(syntax_errors), 0, f"Expected at least one invalid JavaScript error, got: {syntax_errors}")

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
        js_show_if_errors = [e for e in errs if 'js show if' in e.err_str.lower() or 'invalid javascript' in e.err_str.lower()]
        self.assertEqual(len(js_show_if_errors), 0, f"Expected no js show if errors, got: {js_show_if_errors}")

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
        show_if_errors = [e for e in errs if 'show if' in e.err_str.lower() and 'not defined' in e.err_str.lower()]
        self.assertEqual(len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}")

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
        show_if_errors = [e for e in errs if 'show if' in e.err_str.lower() and 'not defined' in e.err_str.lower()]
        self.assertEqual(len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}")

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
        show_if_errors = [e for e in errs if 'show if' in e.err_str.lower() and 'not defined' in e.err_str.lower()]
        self.assertEqual(len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}")

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
        show_if_errors = [e for e in errs if 'show if' in e.err_str.lower() and 'not defined' in e.err_str.lower()]
        self.assertEqual(len(show_if_errors), 0, f"Expected no show if errors, got: {show_if_errors}")

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
        self.assertTrue(any('not defined on this screen' in e.err_str.lower() for e in errs), f"Expected 'not defined on screen' error, got: {errs}")

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
        self.assertTrue(any('show if: variable must be a string' in e.err_str.lower() for e in errs), f"Expected show if variable type error, got: {errs}")

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
        show_if_errors = [e for e in errs if 'show if' in e.err_str.lower() and 'not defined' in e.err_str.lower()]
        self.assertEqual(len(show_if_errors), 0, f"Expected no show if errors with code, got: {show_if_errors}")

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
        self.assertTrue(any('not defined on this screen' in e.err_str.lower() for e in errs), f"Expected 'not defined on screen' error, got: {errs}")

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
        self.assertTrue(any('hide if: variable must be a string' in e.err_str.lower() for e in errs), f"Expected hide if variable type error, got: {errs}")

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
        js_show_if_errors = [e for e in errs if 'js show if' in e.err_str.lower() or 'val()' in e.err_str]
        self.assertEqual(len(js_show_if_errors), 0, f"Expected no js show if errors, got: {js_show_if_errors}")

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
                'js hide if' in e.err_str.lower()
                or ('val()' in e.err_str and 'hide' not in e.err_str.lower())
                or 'invalid javascript' in e.err_str.lower()
            )
        ]
        self.assertEqual(len(js_errors), 0, f"Expected no js hide if errors, got: {js_errors}")

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
            any('invalid javascript syntax in js hide if' in e.err_str.lower() for e in errs),
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
        self.assertEqual(len(errs), 0, f"Expected no errors for valid code block, got: {errs}")

    def test_python_code_block_invalid(self):
        """Error: top-level code block with invalid Python"""
        invalid = """
code: |
  if True
    x = 1
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        self.assertTrue(any('python syntax error' in e.err_str.lower() for e in errs), f"Expected Python syntax error, got: {errs}")

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
        self.assertFalse(any('show if: code has python syntax error' in e.err_str.lower() for e in errs), f"Expected no show if code errors, got: {errs}")

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
        self.assertTrue(any('show if: code has python syntax error' in e.err_str.lower() for e in errs), f"Expected show if code syntax error, got: {errs}")

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
        self.assertFalse(any('python syntax error' in e.err_str.lower() for e in errs), f"Unexpected Python syntax error: {errs}")
        self.assertFalse(any('does not call validation_error' in e.err_str.lower() for e in errs), f"Unexpected missing validation_error warning: {errs}")

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
        self.assertTrue(any('python syntax error' in e.err_str.lower() for e in errs), f"Expected Python syntax error in validation code, got: {errs}")

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
        self.assertTrue(any('does not call validation_error' in e.err_str.lower() for e in errs), f"Expected missing validation_error warning, got: {errs}")

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
        self.assertFalse(any('does not call validation_error' in e.err_str.lower() for e in errs), f"Did not expect missing validation_error warning for pure transformation code, got: {errs}")

    def test_validation_code_transformation_with_conditional_warns(self):
        """Warn when validation code has assignments but also contains a conditional (not transformation-only)"""
        invalid = """
question: |
  What is your phone number?
fields:
  - Phone number: phone_number
validation code: |
  if True:
    phone_number = phone_number.strip()
"""
        errs = find_errors_from_string(invalid, input_file="<string_invalid>")
        # Should warn because although there's an assignment, the presence of a conditional
        # means this is not a pure transformation and the code should likely call validation_error
        self.assertTrue(any('does not call validation_error' in e.err_str.lower() for e in errs), f"Expected missing validation_error warning when conditional present, got: {errs}")

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
        field_errors = [e for e in errs if 'fields should be a list' in e.err_str.lower() or 'fields dict must have' in e.err_str.lower()]
        self.assertEqual(len(field_errors), 0, f"Expected no fields-shape errors, got: {field_errors}")


if __name__ == '__main__':
    unittest.main()
