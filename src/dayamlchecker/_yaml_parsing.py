from __future__ import annotations

import re

DOCUMENT_MATCH = re.compile(r"^--- *$", flags=re.MULTILINE)
_REMOVE_TRAILING_DOTS_RE = re.compile(r"[\n\r]+\.\.\.$")
_TAB_RE = re.compile(r"\t")


def normalize_yaml_for_parser(text: str) -> str:
    """Normalize parser-hostile whitespace before ruamel reads YAML."""
    return _TAB_RE.sub("  ", text)


def normalize_yaml_document_for_parser(source_code: str) -> str:
    """Apply the shared per-document normalization used by validation."""
    return _REMOVE_TRAILING_DOTS_RE.sub("", normalize_yaml_for_parser(source_code))
