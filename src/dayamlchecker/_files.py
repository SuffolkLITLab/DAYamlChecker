"""Shared file-collection utilities used by both the formatter and the checker."""

from __future__ import annotations

import os
from pathlib import Path


def _is_default_ignored_dir(dirname: str) -> bool:
    """Return True for directory names that should be skipped by default."""
    return (
        dirname.startswith(".git")
        or dirname.startswith(".github")
        or dirname.startswith(".venv")
        or dirname == "build"
        or dirname == "dist"
        or dirname == "node_modules"
        or dirname == "sources"
    )


def _collect_yaml_files(
    paths: list[Path],
    check_all: bool = False,
    include_default_ignores: bool | None = None,
) -> list[Path]:
    """Expand paths to a de-duplicated, sorted list of YAML files.

    - Files are included if they have .yml or .yaml extension
    - Directories are recursively searched for YAML files
    """
    if include_default_ignores is None:
        include_default_ignores = not check_all

    yaml_files: list[Path] = []
    for path in paths:
        if path.is_dir():
            # Recursively find all YAML files, pruning ignored directories
            for root, dirnames, filenames in os.walk(path, topdown=True):
                root_path = Path(root)
                if include_default_ignores:
                    if _is_default_ignored_dir(root_path.name):
                        dirnames[:] = []
                        continue
                    dirnames[:] = [
                        d for d in dirnames if not _is_default_ignored_dir(d)
                    ]
                for filename in filenames:
                    if filename.lower().endswith((".yml", ".yaml")):
                        yaml_files.append(root_path / filename)
        elif path.suffix.lower() in (".yml", ".yaml"):
            yaml_files.append(path)
    seen = set()
    result = []
    for f in yaml_files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(f)
    return sorted(result)
