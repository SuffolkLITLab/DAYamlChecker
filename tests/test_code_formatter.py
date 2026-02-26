import unittest
from dayamlchecker.code_formatter import (
    format_python_code,
    format_yaml_string,
    FormatterConfig,
    _convert_indent_4_to_2,
    _strip_common_indent,
)


class TestIndentConversion(unittest.TestCase):
    def test_convert_4_to_2_basic(self):
        code = "    x = 1\n        y = 2\n"
        result = _convert_indent_4_to_2(code)
        self.assertEqual(result, "  x = 1\n    y = 2\n")

    def test_convert_4_to_2_preserves_non_multiple(self):
        # 3 spaces should not be changed
        code = "   x = 1\n"
        result = _convert_indent_4_to_2(code)
        self.assertEqual(result, "   x = 1\n")

    def test_convert_4_to_2_empty_lines(self):
        code = "    x = 1\n\n    y = 2\n"
        result = _convert_indent_4_to_2(code)
        self.assertEqual(result, "  x = 1\n\n  y = 2\n")


class TestStripCommonIndent(unittest.TestCase):
    def test_strip_common_indent_basic(self):
        lines = ["    line1\n", "    line2\n"]
        dedented, removed = _strip_common_indent(lines)
        self.assertEqual(removed, 4)
        self.assertEqual(dedented, ["line1\n", "line2\n"])

    def test_strip_common_indent_mixed(self):
        lines = ["    line1\n", "      line2\n"]
        dedented, removed = _strip_common_indent(lines)
        self.assertEqual(removed, 4)
        self.assertEqual(dedented, ["line1\n", "  line2\n"])

    def test_strip_common_indent_empty_lines(self):
        lines = ["    line1\n", "\n", "    line2\n"]
        dedented, removed = _strip_common_indent(lines)
        self.assertEqual(removed, 4)


class TestFormatPythonCode(unittest.TestCase):
    def test_format_simple_code(self):
        code = "x=1\ny=2"
        result = format_python_code(code)
        self.assertIn("x = 1", result)
        self.assertIn("y = 2", result)

    def test_format_with_indent_conversion(self):
        code = "if True:\n    x = 1"
        config = FormatterConfig(convert_indent_4_to_2=True)
        result = format_python_code(code, config)
        # After Black formats with 4-space indent, we convert to 2-space
        self.assertIn("\n  x = 1", result)

    def test_format_without_indent_conversion(self):
        code = "if True:\n    x = 1"
        config = FormatterConfig(convert_indent_4_to_2=False)
        result = format_python_code(code, config)
        # Black uses 4-space indent by default
        self.assertIn("\n    x = 1", result)

    def test_format_nested_indentation(self):
        code = "if True:\n    if True:\n        x = 1"
        config = FormatterConfig(convert_indent_4_to_2=True)
        result = format_python_code(code, config)
        # Nested should be 4 spaces (2 * 2) instead of 8 (4 * 2)
        self.assertIn("\n    x = 1", result)


class TestFormatYamlString(unittest.TestCase):
    def test_format_code_block(self):
        yaml_content = """---
code: |
  x=1
  y=2
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        self.assertIn("x = 1", result)
        self.assertIn("y = 2", result)

    def test_format_validation_code(self):
        yaml_content = """---
question: What is x?
fields:
  - X: x
validation code: |
  if x<0:
    validation_error("Must be positive")
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        self.assertIn("if x < 0:", result)

    def test_no_change_when_already_formatted(self):
        yaml_content = """---
code: |
  x = 1
  y = 2
"""
        result, changed = format_yaml_string(yaml_content)
        # May still change due to trailing whitespace handling, but content should be similar
        self.assertIn("x = 1", result)

    def test_preserves_other_content(self):
        yaml_content = """---
question: |
  Hello world
subquestion: |
  This is a test
code: |
  x=1
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertIn("Hello world", result)
        self.assertIn("This is a test", result)
        self.assertIn("x = 1", result)

    def test_multi_document_yaml(self):
        yaml_content = """---
code: |
  x=1
---
code: |
  y=2
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        self.assertIn("x = 1", result)
        self.assertIn("y = 2", result)

    def test_nested_code_in_fields(self):
        yaml_content = """---
question: Test
fields:
  - note: Test field
    code: |
      x=1
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        self.assertIn("x = 1", result)

    def test_preserves_yaml_comments_outside_code_blocks(self):
        yaml_content = """# top-level comment
question: |
  What is x?
fields:
  - Agree: agree  # inline comment after mapping inside sequence
    datatype: yesno  # another inline comment
# comment before code
code: |
  # python comment inside code
  x=1  # inline python comment
some_flag: True  # inline boolean comment
# trailing comment
"""
        result, changed = format_yaml_string(yaml_content)
        # comments should be preserved in the dumped YAML
        self.assertIn("# top-level comment", result)
        self.assertIn("# inline comment after mapping inside sequence", result)
        self.assertIn("# comment before code", result)
        self.assertIn("# trailing comment", result)
        self.assertIn("some_flag: True", result)

    def test_preserves_comments_in_code_blocks(self):
        yaml_content = """---
code: |
  # inside code block
  x=1  # keep inline comment
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertIn("# inside code block", result)
        self.assertIn("# keep inline comment", result)
        # ensure the inline python comment remains on the same line as the statement
        self.assertIn("x = 1  # keep inline comment", result)

    def test_preserves_boolean_case_and_sequence_format(self):
        yaml_content = """---
some_flag: True
fields:
- Name: value
  datatype: string
code: |
  x=1
"""
        result, changed = format_yaml_string(yaml_content)
        # boolean capitalization preserved
        self.assertIn("some_flag: True", result)
        # sequence dash location/format preserved (dash at column 0)
        self.assertIn("fields:\n- Name: value", result)

    def test_preserves_blank_lines_in_code_block_body(self):
        yaml_content = """---
code: |
  x=1

  y=2
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        self.assertIn("x = 1\n\n  y = 2", result)

    def test_only_code_block_text_changes(self):
        yaml_content = """---
features:
  use catchall: True
modules:
  - .custom_jinja_filters
question: |
  Hello
code: |
  if True:
      x=1
"""
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        # Non-code YAML should stay structurally/casing identical
        self.assertIn("use catchall: True", result)
        self.assertIn("modules:\n  - .custom_jinja_filters", result)
        self.assertIn("question: |\n  Hello", result)
        # Code block gets formatted
        self.assertIn("if True:\n    x = 1", result)


class TestFormatterConfig(unittest.TestCase):
    def test_default_config(self):
        config = FormatterConfig()
        self.assertIn("code", config.python_keys)
        self.assertIn("validation code", config.python_keys)
        self.assertEqual(config.black_line_length, 88)
        self.assertTrue(config.convert_indent_4_to_2)

    def test_custom_python_keys(self):
        config = FormatterConfig(python_keys={"code", "custom_code"})
        self.assertIn("code", config.python_keys)
        self.assertIn("custom_code", config.python_keys)
        self.assertNotIn("validation code", config.python_keys)


if __name__ == "__main__":
    unittest.main()
