#!/usr/bin/env python3
"""Compatibility wrapper for the packaged deterministic YAML fixer."""

from dayamlchecker.fixer import FilePlan, TextEdit, apply_plan, main, plan_file, run
from dayamlchecker.fixer import _target_counts

__all__ = [
    "FilePlan",
    "TextEdit",
    "_target_counts",
    "apply_plan",
    "main",
    "plan_file",
    "run",
]


if __name__ == "__main__":
    raise SystemExit(main())
