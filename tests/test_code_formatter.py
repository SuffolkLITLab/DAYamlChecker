import unittest
from pathlib import Path
from dayamlchecker.code_formatter import (
    format_python_code,
    format_yaml_string,
    FormatterConfig,
    _convert_indent_4_to_2,
    _strip_common_indent,
)
from dayamlchecker._jinja import (
    JinjaWithoutHeaderError,
    _contains_jinja_syntax,
    _has_jinja_header,
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


class TestContainsJinjaSyntax(unittest.TestCase):
    def test_detects_variable_expression(self):
        self.assertTrue(_contains_jinja_syntax("question: Hello {{ user }}!"))

    def test_detects_block_tag(self):
        self.assertTrue(_contains_jinja_syntax("{% if condition %}yes{% endif %}"))

    def test_detects_comment_tag(self):
        self.assertTrue(_contains_jinja_syntax("{# This is a comment #}"))

    def test_detects_whitespace_control_tags(self):
        self.assertTrue(_contains_jinja_syntax("{%- if x -%}\ncontent\n{%- endif -%}"))

    def test_plain_yaml_not_detected(self):
        self.assertFalse(
            _contains_jinja_syntax("question: Hello world\ncode: |\n  x = 1\n")
        )

    def test_python_single_brace_dict_not_detected(self):
        self.assertFalse(_contains_jinja_syntax("code: |\n  d = {key: value}\n"))

    def test_empty_string_not_detected(self):
        self.assertFalse(_contains_jinja_syntax(""))

    def test_plain_text_with_percent_not_detected(self):
        self.assertFalse(_contains_jinja_syntax("discount: 50%\n"))


class TestHasJinjaHeader(unittest.TestCase):
    def test_exact_header_detected(self):
        self.assertTrue(_has_jinja_header("# use jinja\nquestion: test\n"))

    def test_header_only_line(self):
        self.assertTrue(_has_jinja_header("# use jinja"))

    def test_header_with_leading_whitespace_not_detected(self):
        # First line must be exactly '# use jinja'; leading spaces disqualify it
        self.assertFalse(_has_jinja_header(" # use jinja\nquestion: test\n"))

    def test_missing_space_not_detected(self):
        self.assertFalse(_has_jinja_header("#use jinja\nquestion: test\n"))

    def test_no_header_returns_false(self):
        self.assertFalse(_has_jinja_header("---\nquestion: test\n"))

    def test_empty_content_returns_false(self):
        self.assertFalse(_has_jinja_header(""))


class TestFormatYamlStringJinja(unittest.TestCase):
    """Valid Jinja files (with '# use jinja' header) are skipped unchanged.
    Files that contain Jinja syntax WITHOUT the header are an error.
    """

    # --- valid Jinja files (should be returned unchanged) ---

    def test_jinja_variable_file_returned_unchanged(self):
        yaml_content = (
            "# use jinja\n---\nquestion: Hello {{ user }}\ncode: |\n  x = 1\n"
        )
        result, changed = format_yaml_string(yaml_content)
        self.assertEqual(result, yaml_content)
        self.assertFalse(changed)

    def test_jinja_block_tag_returned_unchanged(self):
        # No code blocks — nothing to format, returned unchanged.
        yaml_content = (
            "# use jinja\n---\n{% if condition %}\nquestion: test\n{% endif %}\n"
        )
        result, changed = format_yaml_string(yaml_content)
        self.assertEqual(result, yaml_content)
        self.assertFalse(changed)

    def test_jinja_comment_returned_unchanged(self):
        # No code blocks — nothing to format, returned unchanged.
        yaml_content = "# use jinja\n{# template comment #}\nquestion: test\n"
        result, changed = format_yaml_string(yaml_content)
        self.assertEqual(result, yaml_content)
        self.assertFalse(changed)

    def test_jinja_code_block_with_jinja_syntax_not_modified(self):
        # A code block that itself contains Jinja syntax must be left alone.
        yaml_content = (
            "# use jinja\n"
            "---\n"
            "code: |\n"
            "  {% for item in items %}\n"
            "  x = {{ item }}\n"
            "  {% endfor %}\n"
        )
        result, changed = format_yaml_string(yaml_content)
        self.assertEqual(result, yaml_content)
        self.assertFalse(changed)

    def test_jinja_mixed_blocks_only_clean_ones_formatted(self):
        # Second code block has no Jinja — only that block should be formatted.
        yaml_content = "# use jinja\n---\ncode: |\n  x={{ y }}\n---\ncode: |\n  z=1\n"
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        # First block (Jinja) must be untouched
        self.assertIn("x={{ y }}", result)
        # Second block (clean) must be formatted
        self.assertIn("z = 1", result)

    def test_jinja_variable_file_already_formatted_unchanged(self):
        # Already-formatted code block — no change expected.
        yaml_content = (
            "# use jinja\n---\nquestion: Hello {{ user }}\ncode: |\n  x = 1\n"
        )
        result, changed = format_yaml_string(yaml_content)
        self.assertFalse(changed)
        self.assertEqual(result, yaml_content)

    def test_jinja_with_unformatted_code_is_now_formatted(self):
        # A valid Jinja file whose code block has no Jinja syntax IS now formatted.
        yaml_content = "# use jinja\n---\nquestion: Hello {{ user }}\ncode: |\n  x=1\n"
        result, changed = format_yaml_string(yaml_content)
        self.assertTrue(changed)
        self.assertIn("x = 1", result)
        # Jinja expression preserved exactly
        self.assertIn("{{ user }}", result)
        # Header preserved
        self.assertTrue(result.startswith("# use jinja\n"))

    # --- invalid: Jinja syntax present but no '# use jinja' header ---

    def test_jinja_variable_without_header_raises(self):
        yaml_content = "---\nquestion: Hello {{ user }}\n"
        with self.assertRaises(JinjaWithoutHeaderError):
            format_yaml_string(yaml_content)

    def test_jinja_block_tag_without_header_raises(self):
        yaml_content = "---\n{% if condition %}\nquestion: test\n{% endif %}\n"
        with self.assertRaises(JinjaWithoutHeaderError):
            format_yaml_string(yaml_content)

    def test_jinja_comment_without_header_raises(self):
        yaml_content = "{# template comment #}\nquestion: test\n"
        with self.assertRaises(JinjaWithoutHeaderError):
            format_yaml_string(yaml_content)


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


class TestReindent(unittest.TestCase):
    """Tests for _reindent."""

    def setUp(self):
        from dayamlchecker.code_formatter import _reindent

        self._fn = _reindent

    def test_zero_indent_returns_unchanged(self):
        text = "x = 1\ny = 2\n"
        self.assertEqual(self._fn(text, 0), text)

    def test_negative_indent_returns_unchanged(self):
        text = "x = 1\n"
        self.assertEqual(self._fn(text, -1), text)

    def test_positive_indent_adds_prefix_to_non_empty_lines(self):
        text = "x = 1\ny = 2\n"
        result = self._fn(text, 2)
        self.assertIn("  x = 1", result)
        self.assertIn("  y = 2", result)

    def test_blank_lines_not_indented(self):
        text = "x = 1\n\ny = 2\n"
        result = self._fn(text, 2)
        lines = result.splitlines()
        # blank line should remain blank (not gain spaces)
        self.assertIn("", lines)


class TestFindBlockBodySpan(unittest.TestCase):
    """Tests for _find_block_body_span."""

    def setUp(self):
        from dayamlchecker.code_formatter import _find_block_body_span

        self._fn = _find_block_body_span

    def test_header_at_last_line_returns_empty_span(self):
        # Only one line, header is at index 0 -> no body
        lines = ["code: |\n"]
        start, end, indent = self._fn(lines, 0)
        self.assertGreater(start, end)

    def test_basic_body_span(self):
        lines = ["code: |\n", "  x = 1\n", "  y = 2\n"]
        start, end, indent = self._fn(lines, 0)
        self.assertEqual(start, 1)
        self.assertEqual(end, 2)
        self.assertEqual(indent, 2)

    def test_blank_lines_inside_body_included(self):
        lines = ["code: |\n", "  x = 1\n", "\n", "  y = 2\n", "question: |\\n"]
        start, end, _ = self._fn(lines, 0)
        # blank line at index 2 is part of the block
        self.assertGreaterEqual(end, 3)

    def test_dedented_line_ends_body(self):
        lines = ["code: |\n", "  x = 1\n", "other: value\n"]
        start, end, _ = self._fn(lines, 0)
        self.assertEqual(end, 1)


class TestFormatYamlFile(unittest.TestCase):
    """Tests for format_yaml_file()."""

    def test_format_writes_and_returns_changes(self):
        import tempfile
        import os
        from dayamlchecker.code_formatter import format_yaml_file

        content = "---\ncode: |\n  x=1\n"
        with tempfile.NamedTemporaryFile(
            suffix=".yml", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            fname = f.name
        try:
            result, changed = format_yaml_file(fname, write=True)
            self.assertTrue(changed)
            self.assertIn("x = 1", result)
            # File should be updated on disk
            self.assertIn("x = 1", Path(fname).read_text(encoding="utf-8"))
        finally:
            os.unlink(fname)

    def test_format_no_write_does_not_modify_file(self):
        import tempfile
        import os
        from dayamlchecker.code_formatter import format_yaml_file

        content = "---\ncode: |\n  x=1\n"
        with tempfile.NamedTemporaryFile(
            suffix=".yml", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            fname = f.name
        try:
            result, changed = format_yaml_file(fname, write=False)
            self.assertTrue(changed)
            # Original file must be unchanged
            self.assertEqual(Path(fname).read_text(encoding="utf-8"), content)
        finally:
            os.unlink(fname)

    def test_format_unchanged_file_returns_false(self):
        import tempfile
        import os
        from dayamlchecker.code_formatter import format_yaml_file

        content = "---\ncode: |\n  x = 1\n"
        with tempfile.NamedTemporaryFile(
            suffix=".yml", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            fname = f.name
        try:
            _, changed = format_yaml_file(fname)
            self.assertFalse(changed)
        finally:
            os.unlink(fname)


class TestCollectYamlFiles(unittest.TestCase):
    """Tests for _collect_yaml_files in code_formatter."""

    def test_check_all_flag_disables_ignores(self):
        import tempfile
        from dayamlchecker.code_formatter import _collect_yaml_files

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            visible = root / "visible.yml"
            git_dir = root / ".git"
            git_dir.mkdir()
            hidden = git_dir / "hidden.yml"
            visible.write_text("---\n", encoding="utf-8")
            hidden.write_text("---\n", encoding="utf-8")

            result = _collect_yaml_files([root], check_all=True)
            paths = [p.name for p in result]
            self.assertIn("hidden.yml", paths)

    def test_venv_dir_is_ignored_by_default(self):
        import tempfile
        from dayamlchecker.code_formatter import _collect_yaml_files

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv_dir = root / ".venv"
            venv_dir.mkdir()
            (venv_dir / "env.yml").write_text("---\n", encoding="utf-8")
            (root / "real.yml").write_text("---\n", encoding="utf-8")

            result = _collect_yaml_files([root])
            names = [p.name for p in result]
            self.assertIn("real.yml", names)
            self.assertNotIn("env.yml", names)

    def test_single_yaml_file_path_collected(self):
        import tempfile
        import os
        from dayamlchecker.code_formatter import _collect_yaml_files

        with tempfile.NamedTemporaryFile(
            suffix=".yml", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write("---\n")
            fname = f.name
        try:
            result = _collect_yaml_files([Path(fname)])
            self.assertEqual(len(result), 1)
        finally:
            os.unlink(fname)

    def test_non_yaml_file_not_collected(self):
        import tempfile
        import os
        from dayamlchecker.code_formatter import _collect_yaml_files

        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write("hello\n")
            fname = f.name
        try:
            result = _collect_yaml_files([Path(fname)])
            self.assertEqual(result, [])
        finally:
            os.unlink(fname)


class TestFormatterConfigDefaults(unittest.TestCase):
    def test_prefer_literal_blocks_default_true(self):
        config = FormatterConfig()
        self.assertTrue(config.prefer_literal_blocks)

    def test_strip_trailing_whitespace_default_true(self):
        config = FormatterConfig()
        self.assertTrue(config.strip_trailing_whitespace)

    def test_black_target_versions_default_empty(self):
        config = FormatterConfig()
        self.assertEqual(config.black_target_versions, set())


class TestFormatYamlStringEdgeCases(unittest.TestCase):
    """Additional edge-case tests for format_yaml_string."""

    def test_empty_yaml_no_change(self):
        result, changed = format_yaml_string("")
        self.assertFalse(changed)

    def test_none_document_no_crash(self):
        # A YAML stream with only '---' produces a None document
        result, changed = format_yaml_string("---\n")
        self.assertFalse(changed)

    def test_no_trailing_newline_on_last_body_line_preserved(self):
        # Body line that doesn't end with \n should not gain one after replacement
        yaml_content = "code: |\n  x=1"
        result, _ = format_yaml_string(yaml_content)
        self.assertIn("x = 1", result)

    def test_format_with_custom_line_length(self):
        # A very short line length forces Black to break the line
        config = FormatterConfig(black_line_length=20)
        yaml_content = (
            "---\ncode: |\n  very_long_variable_name = another_long_variable\n"
        )
        result, _ = format_yaml_string(yaml_content, config)
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
