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


if __name__ == '__main__':
    unittest.main()
