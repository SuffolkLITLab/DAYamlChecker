import tempfile
import unittest
from pathlib import Path

from dayamlchecker.fixer import (
    FixOptions,
    _target_counts,
    apply_plan,
    plan_file,
)
from dayamlchecker.yaml_structure import DEFAULT_LINT_MODE


class TestYAMLCheckerFixer(unittest.TestCase):
    def test_fixer_handles_ids_shortcuts_labels_and_duplicate_ids(self) -> None:
        source = """---
question: What is your name?
yesno: user_agrees
---
question: What is your name?
fields:
  - no label: first_name
  - no label: last_name
---
id: duplicate
question: First duplicate
---
id: duplicate
question: Second duplicate
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interview.yml"
            path.write_text(source, encoding="utf-8")

            before = _target_counts(source, path)
            plan = plan_file(path)
            self.assertIsNone(plan.skipped_reason)
            self.assertIsNone(plan.validation_error)
            self.assertEqual(
                plan.counts, {"EA502": 1, "EA510": 1, "EG104": 1, "EG414": 2}
            )

            apply_plan(plan, write=True)
            result = path.read_text(encoding="utf-8")
            after = _target_counts(result, path)

            self.assertEqual(before["EG414"], 2)
            self.assertEqual(before["EA510"], 1)
            self.assertEqual(before["EG104"], 1)
            self.assertEqual(after["EG414"], 0)
            self.assertEqual(after["EA510"], 0)
            self.assertEqual(after["EG104"], 0)
            self.assertLess(after["EA502"], before["EA502"])
            self.assertIn('id: "what is your name"', result)
            self.assertIn('id: "what is your name 2"', result)
            self.assertIn('id: "duplicate 2"', result)
            self.assertIn('"What is your name?": first_name', result)

            second_plan = plan_file(path)
            self.assertFalse(second_plan.changed)
            self.assertEqual(second_plan.counts, {})

    def test_fixer_preserves_yesnomaybe_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "yesnomaybe.yml"
            path.write_text(
                "question: Continue?\nyesnomaybe: continue\n", encoding="utf-8"
            )

            plan = plan_file(path)
            self.assertIsNone(plan.validation_error)
            apply_plan(plan, write=True)
            result = path.read_text(encoding="utf-8")

            self.assertIn("datatype: yesnomaybe", result)
            self.assertNotIn("yesnomaybe:", result)
            self.assertEqual(_target_counts(result, path)["EA510"], 0)

    def test_fixer_labels_blank_mapping_key_in_place(self) -> None:
        source = """question: Child support?
fields:
  - "": pays_child_support  
    datatype: yesnoradio
  - Amount: child_support_amount
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blank-label.yml"
            path.write_text(source, encoding="utf-8")

            plan = plan_file(path)
            self.assertIsNone(plan.validation_error)
            apply_plan(plan, write=True)
            result = path.read_text(encoding="utf-8")

            self.assertIn('  - "Child support?": pays_child_support', result)
            self.assertNotIn("pays_child_support  ", result)
            self.assertNotIn("label:", result)
            self.assertEqual(_target_counts(result, path)["EA502"], 0)
            self.assertFalse(plan_file(path).changed)

    def test_fixer_rewrites_block_scalar_duplicate_id(self) -> None:
        source = """---
id: |
  same screen
question: First
---
id: |
  same screen
question: Second
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "block-id.yml"
            path.write_text(source, encoding="utf-8")

            plan = plan_file(path)
            self.assertIsNone(plan.validation_error)
            apply_plan(plan, write=True)
            result = path.read_text(encoding="utf-8")

            self.assertIn("  same screen 2\n", result)
            self.assertEqual(_target_counts(result, path)["EG104"], 0)

    def test_dry_run_does_not_modify_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dry-run.yml"
            source = "question: What is your name?\n"
            path.write_text(source, encoding="utf-8")

            plan = plan_file(path)
            apply_plan(plan, write=False)

            self.assertEqual(path.read_text(encoding="utf-8"), source)

    def _fixed(self, source: str, name: str = "interview.yml") -> tuple[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / name
            path.write_text(source, encoding="utf-8")
            plan = plan_file(path)
            apply_plan(plan, write=True)
            return path.read_text(encoding="utf-8"), plan

    def test_fixer_leaves_screens_with_two_shortcuts_alone(self) -> None:
        source = "id: two\nquestion: Agree?\nyesno: a\nnoyes: b\n"
        result, plan = self._fixed(source, "two-shortcuts.yml")

        # One replacement per shortcut would write two ``fields`` keys.
        self.assertEqual(result, source)
        self.assertEqual(result.count("fields:"), 0)
        self.assertEqual(plan.counts, {})

    def test_fixer_adds_label_as_a_sibling_of_a_sequence_field(self) -> None:
        source = (
            "id: seq\nquestion: |\n  What is your name?\n"
            "fields:\n  - field: user_name\n  - Second thing: other_var\n"
        )
        result, _ = self._fixed(source, "sequence-field.yml")

        self.assertIn('  - field: user_name\n    label: "What is your name?"\n', result)
        # A copied ``- `` prefix would add a third field instead of a label.
        self.assertEqual(result.count("  - "), 2)
        self.assertEqual(_target_counts(result, Path("sequence-field.yml"))["EA502"], 0)

    def test_fixer_replaces_boolean_no_label_with_a_label(self) -> None:
        source = (
            "id: bool\nquestion: |\n  Do you agree?\n"
            "fields:\n  - no label: true\n    field: user_agrees\n"
            "  - Second thing: other_var\n"
        )
        result, _ = self._fixed(source, "bool-no-label.yml")

        # ``true`` is a modifier, not the field's variable name.
        self.assertIn('  - label: "Do you agree?"\n    field: user_agrees\n', result)
        self.assertNotIn('"Do you agree?": true', result)
        self.assertNotIn("no label", result)

    def test_fixer_labels_the_first_offending_field_not_the_first_field(self) -> None:
        source = (
            "id: later\nquestion: Income?\n"
            "fields:\n  - Employer: employer_name\n  - no label: income_amount\n"
        )
        result, plan = self._fixed(source, "later-offender.yml")

        self.assertEqual(plan.counts, {"EA502": 1})
        self.assertIn('  - "Income?": income_amount\n', result)

    def test_fixer_skips_code_fields_like_the_checker(self) -> None:
        source = (
            "id: code\nquestion: Income?\n"
            "fields:\n  - no label: choices\n    code: options\n"
            "  - no label: income_amount\n"
        )
        result, plan = self._fixed(source, "code-field.yml")

        # The checker never reports the ``code`` field, so neither may the fixer.
        self.assertIn("  - no label: choices\n    code: options\n", result)
        self.assertIn('  - "Income?": income_amount\n', result)
        self.assertEqual(plan.counts, {"EA502": 1})

    def test_fixer_leaves_folded_multiline_ids_alone(self) -> None:
        source = (
            "id: >\n  same\n  screen\nquestion: First\n---\n"
            "id: >\n  same\n  screen\nquestion: Second\n"
        )
        result, plan = self._fixed(source, "folded-id.yml")

        # Rewriting only the first content line would fold the remaining lines
        # onto the new ID, producing "same screen 2 screen".
        self.assertEqual(result, source)
        self.assertIsNotNone(plan.skipped_reason)

    def test_fixer_plans_tab_indented_files(self) -> None:
        source = (
            "id: tabbed\nquestion: Agree?\nfields:\n\t- no label: a\n\t- Second: b\n"
        )
        result, plan = self._fixed(source, "tabbed.yml")

        # The checker expands tabs before parsing; the fixer must agree, and
        # must translate the expanded columns back onto the raw line.
        self.assertIsNone(plan.skipped_reason)
        self.assertIn('\t- "Agree?": a\n', result)
        self.assertIn("\t- Second: b\n", result)

    def test_fixer_honors_lint_mode_and_suppressions(self) -> None:
        source = "id: flag\nquestion: Agree?\nyesno: user_agrees\n"
        with tempfile.TemporaryDirectory() as directory:
            for name, options in (
                ("no-wcag.yml", FixOptions(lint_mode=DEFAULT_LINT_MODE)),
                ("suppressed.yml", FixOptions(suppressed_codes=frozenset({"EA510"}))),
            ):
                path = Path(directory) / name
                path.write_text(source, encoding="utf-8")
                plan = plan_file(path, options)
                apply_plan(plan, write=True)

                # The rule is turned off for this run, so nothing to rewrite.
                self.assertEqual(path.read_text(encoding="utf-8"), source, name)
                self.assertEqual(plan.counts, {}, name)

    def test_fixer_rejects_an_edit_that_removes_no_finding(self) -> None:
        from dayamlchecker import fixer

        source = (
            "id: noop\nquestion: |\n  What is your name?\n"
            "fields:\n  - field: user_name\n  - Second thing: other_var\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noop.yml"
            path.write_text(source, encoding="utf-8")

            # Recreate the pre-fix behaviour of copying the ``- `` prefix.
            original = fixer._insert_before_line

            def _sibling_becomes_a_new_item(
                lines, *, line_number, replacement_lines, newline
            ):
                return original(
                    lines,
                    line_number=line_number,
                    replacement_lines=[
                        line.replace("    ", "  - ", 1) for line in replacement_lines
                    ],
                    newline=newline,
                )

            fixer._insert_before_line = _sibling_becomes_a_new_item
            try:
                plan = plan_file(path)
            finally:
                fixer._insert_before_line = original

            self.assertIsNotNone(plan.validation_error)
            self.assertFalse(plan.changed)
            # Counts must describe what was written, not what was attempted.
            self.assertEqual(plan.counts, {})
            apply_plan(plan, write=True)
            self.assertEqual(path.read_text(encoding="utf-8"), source)

    def test_fixer_is_idempotent_on_screens_with_several_bare_fields(self) -> None:
        source = (
            "id: assets\nquestion: |\n  Is anyone holding assets for you?\n"
            "fields:\n  - no label: anyone_holds\n  - no label: anyone_holds_describe\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repeat.yml"
            path.write_text(source, encoding="utf-8")

            first = plan_file(path)
            apply_plan(first, write=True)
            after_first = path.read_text(encoding="utf-8")
            self.assertEqual(first.counts, {"EA502": 1})
            self.assertIn(
                '  - "Is anyone holding assets for you?": anyone_holds\n', after_first
            )

            # The second field is intentionally left for human review, so a
            # repeat run must not spend the same question text on it.
            second = plan_file(path)
            apply_plan(second, write=True)

            self.assertFalse(second.changed)
            self.assertEqual(second.counts, {})
            self.assertEqual(path.read_text(encoding="utf-8"), after_first)

    def test_generated_ids_are_alphanumeric_lowercase(self) -> None:
        source = (
            "---\nquestion: What is your name?\n"
            "---\nquestion: |\n  WHAT is your NAME!?\n"
            "---\nquestion: Does ${ users[0] } agree?\n"
        )
        result, plan = self._fixed(source, "ids.yml")

        self.assertEqual(plan.counts, {"EG414": 3})
        self.assertIn('id: "what is your name"\n', result)
        # Punctuation and case no longer hide a collision from the uniqueness
        # pass, so the second screen is suffixed rather than reading the same.
        self.assertIn('id: "what is your name 2"\n', result)
        self.assertIn('id: "does users 0 agree"\n', result)

    def test_generated_ids_drop_apostrophes_but_separate_on_punctuation(self) -> None:
        source = (
            "---\nquestion: We didn\u2019t find a matching court\n"
            "---\nquestion: ${city_only_address}\n"
        )
        result, _ = self._fixed(source, "punct.yml")

        self.assertIn('id: "we didnt find a matching court"\n', result)
        self.assertIn('id: "city only address"\n', result)

    def test_duplicate_id_fix_keeps_the_author_s_own_text(self) -> None:
        source = (
            "---\nid: My Screen?\nquestion: First\n"
            "---\nid: My Screen?\nquestion: Second\n"
        )
        result, plan = self._fixed(source, "dup.yml")

        # EG104 only has to make an existing ID unique; rewriting the author's
        # own text beyond the suffix is not the fixer's call.
        self.assertEqual(plan.counts, {"EG104": 1})
        self.assertIn("id: My Screen?\n", result)
        self.assertIn('id: "My Screen? 2"\n', result)

    def test_mako_directives_force_a_block_label(self) -> None:
        source = (
            "id: guardian\n"
            "question: |\n"
            "  % if filled_by_attorney:\n"
            "  Does ${ users[0] } want to be the guardian?\n"
            "  % else:\n"
            "  Do you want to be the guardian?\n"
            "  % endif\n"
            "fields:\n"
            "  - no label: wants_guardianship\n"
            "    datatype: yesnoradio\n"
            "  - Something else: other_var\n"
        )
        result, plan = self._fixed(source, "mako.yml")

        # `% if` only works at the start of a line, so the one-line
        # `"question": variable` shorthand cannot carry it; the long form can.
        self.assertEqual(plan.counts, {"EA502": 1})
        self.assertIn(
            "  - label: |\n"
            "      % if filled_by_attorney:\n"
            "      Does ${ users[0] } want to be the guardian?\n"
            "      % else:\n"
            "      Do you want to be the guardian?\n"
            "      % endif\n"
            "    field: wants_guardianship\n"
            "    datatype: yesnoradio\n",
            result,
        )
        self.assertNotIn('"% if', result)

        from ruamel.yaml import YAML

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parsed.yml"
            path.write_text(result, encoding="utf-8")
            doc = YAML().load(path)
            # The label must be the question text verbatim, not a flattened copy.
            self.assertEqual(doc["fields"][0]["label"], doc["question"])
            self.assertEqual(doc["fields"][0]["field"], "wants_guardianship")
            self.assertFalse(plan_file(path).changed)

    def test_inline_mako_expressions_still_use_the_shorthand(self) -> None:
        source = (
            "id: inline\n"
            "question: |\n"
            "  What is ${ other_parties[0].familiar() }'s address?\n"
            "fields:\n"
            "  - no label: other_address\n"
            "  - Something else: other_var\n"
        )
        result, _ = self._fixed(source, "inline-mako.yml")

        # ``${ }`` evaluates fine mid-line, so nothing needs to move.
        self.assertIn(
            '  - "What is ${ other_parties[0].familiar() }\'s address?": other_address\n',
            result,
        )
        self.assertNotIn("label: |", result)
