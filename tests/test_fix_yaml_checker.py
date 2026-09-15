import tempfile
import unittest
from pathlib import Path

from dayamlchecker.fixer import _target_counts, apply_plan, plan_file


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
            self.assertIn('id: "What is your name?"', result)
            self.assertIn('id: "What is your name? 2"', result)
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
