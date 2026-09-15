#!/usr/bin/env python3
"""Apply conservative, formatting-preserving fixes for four DAYamlChecker rules.

The fixer intentionally edits only YAML source lines that correspond to:

* EG414: add an ID to a question block, using normalized question text;
* EA510: expand yes/no shortcuts into an explicit ``fields`` entry;
* EA502: label the first offending input field with the question text;
* EG104: suffix later duplicate block IDs until IDs are unique per YAML file.

The default mode is a dry run. Pass ``--write`` to modify files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ruamel.yaml import YAML

from dayamlchecker.accessibility import (
    _extract_field_label,
    _field_collects_user_input,
)
from dayamlchecker.messages import Finding
from dayamlchecker.yaml_structure import (
    ACCESSIBILITY_LINT_MODE,
    RuntimeOptions,
    _collect_yaml_files,
    _finding_matches_suppression,
    find_errors_from_string,
    fix_tabs,
)

TARGET_CODES = frozenset({"EG414", "EA510", "EA502", "EG104"})
SHORTCUTS = ("yesno", "noyes", "yesnomaybe", "noyesmaybe")


@dataclass(frozen=True)
class FixOptions:
    """The lint settings the fixer must agree with.

    ``--fix`` runs inside the checker, so it has to see exactly the findings
    the checker will report: rewriting source for a rule the user disabled
    with ``--no-wcag`` or ``--suppress`` is never what they asked for.
    """

    lint_mode: str = ACCESSIBILITY_LINT_MODE
    suppressed_codes: frozenset[str] = frozenset()
    runtime_options: RuntimeOptions | None = None


@dataclass(frozen=True)
class TextEdit:
    start: int
    end: int
    replacement: str


@dataclass
class FilePlan:
    path: Path
    edits: list[TextEdit] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    skipped_reason: str | None = None
    validation_error: str | None = None

    @property
    def changed(self) -> bool:
        return (
            bool(self.edits) and not self.skipped_reason and not self.validation_error
        )


@dataclass
class _EditAccumulator:
    """Collect non-overlapping line edits for one YAML file."""

    edits: list[TextEdit] = field(default_factory=list)
    occupied_lines: set[int] = field(default_factory=set)
    counts: Counter[str] = field(default_factory=Counter)

    def add(self, edit: TextEdit, code: str) -> None:
        occupied = set(range(edit.start, max(edit.end, edit.start + 1)))
        if edit.start in self.occupied_lines or (
            edit.end > edit.start and self.occupied_lines.intersection(occupied)
        ):
            raise ValueError(f"overlapping edits near line {edit.start + 1}")
        self.edits.append(edit)
        self.occupied_lines.update(occupied)
        self.counts[code] += 1


def _yaml_loader() -> YAML:
    yaml = YAML(typ="rt")
    # Duplicate block IDs are separate YAML documents, not duplicate YAML keys.
    # Allowing duplicate keys here lets the fixer inspect a file without
    # discarding the user's source before the checker reports it.
    yaml.allow_duplicate_keys = True
    return yaml


def _normalize_for_parsing(text: str) -> str:
    """Expand tabs the way ``find_errors_from_string`` does before parsing.

    Without this the fixer rejects files the checker reads happily. Tabs are
    one character in the source but two columns after expansion, so every
    column ruamel reports is translated back by :func:`_raw_column`.
    """
    return fix_tabs.sub("  ", text)


def _raw_column(raw_line: str, column: int) -> int:
    """Map a column in the tab-expanded line back onto the raw line."""
    if "\t" not in raw_line:
        return column
    expanded = 0
    for index, char in enumerate(raw_line):
        if expanded >= column:
            return index
        expanded += 2 if char == "\t" else 1
    return len(raw_line)


def _load_documents(text: str) -> tuple[list[Any] | None, str | None]:
    try:
        return list(_yaml_loader().load_all(_normalize_for_parsing(text))), None
    except Exception as exc:  # ruamel uses several MarkedYAMLError subclasses
        return None, str(exc)


def _newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _line_ending(line: str, newline: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _quote_yaml_string(value: str) -> str:
    # JSON double-quoted strings are valid YAML scalars and safely handle
    # colons, quotes, brackets, Mako syntax, and HTML in question text.
    return json.dumps(value, ensure_ascii=False)


def _normalized_question(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


# Mako honours ``% if``/``% for`` only at the start of a line, so question
# text using them cannot survive being collapsed into a one-line label.
_MAKO_DIRECTIVE = re.compile(r"^[ \t]*%", re.MULTILINE)


def _question_needs_block_label(value: Any) -> bool:
    return isinstance(value, str) and bool(_MAKO_DIRECTIVE.search(value))


def _question_block_lines(value: Any) -> list[str]:
    """The question's own lines, trailing blanks dropped, Mako left as written."""
    return str(value).rstrip().splitlines()


def _block_label_edit(
    lines: list[str],
    *,
    line_number: int,
    column: int,
    question: Any,
    variable: str | None,
    newline: str,
) -> TextEdit | None:
    """Rewrite a field's first line as a multi-line ``label:`` block.

    The one-line ``"question": variable`` shorthand cannot hold a line break,
    so a question carrying Mako line directives has to move to the
    ``label:``/``field:`` form, where a literal block scalar keeps the
    directives on their own lines exactly as the author wrote them.
    """
    body = lines[line_number].rstrip("\r\n")
    colon = body.find(":", column)
    if colon < 0:
        return None
    _, comment = _split_inline_comment(body, colon + 1)
    question_lines = _question_block_lines(question)
    if not question_lines:
        return None

    marker = body[:column]
    key_indent = " " * column
    content_indent = " " * (column + 2)
    replacement = [marker + "label: |" + ((" " + comment) if comment else "")]
    replacement += [
        content_indent + line if line.strip() else "" for line in question_lines
    ]
    if variable is not None:
        replacement.append(key_indent + "field: " + variable)
    ending = _line_ending(lines[line_number], newline)
    return TextEdit(
        start=line_number,
        end=line_number + 1,
        replacement=newline.join(replacement) + ending,
    )


def _normalized_id(value: Any) -> str:
    """Normalize question text into a block ID.

    An ID only has to be unique and readable, so nothing but letters, digits
    and spaces survives: punctuation, Mako delimiters and smart quotes all
    make an ID awkward to quote and to reference. Lowercasing means two
    questions that differ only in case or punctuation collide here rather than
    producing two IDs that read identically.

    Apostrophes are dropped rather than separated on, so ``didn't`` becomes
    ``didnt`` instead of ``didn t``; every other mark becomes a space, so
    ``city_only_address`` stays three readable words.
    """
    text = re.sub(r"['\u2018\u2019\u02bc]", "", _normalized_question(value))
    text = "".join(char if char.isalnum() else " " for char in text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "on"}
    return False


def _split_inline_comment(line: str, start: int) -> tuple[str, str]:
    """Split a YAML line after start into value text and a trailing comment."""
    quote: str | None = None
    escaped = False
    for index in range(start, len(line)):
        char = line[index]
        if quote == '"' and escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if quote and char == quote:
            quote = None
            continue
        if not quote and char in {"'", '"'}:
            quote = char
            continue
        if not quote and char == "#" and (index == start or line[index - 1].isspace()):
            return line[start:index].rstrip(), line[index:].rstrip()
    return line[start:].rstrip(), ""


def _key_column(
    document: Any, key: str, lines: list[str] | None = None
) -> tuple[int, int] | None:
    try:
        line, column = document.lc.key(key)
    except (AttributeError, KeyError, TypeError):
        return None
    if lines is not None and 0 <= line < len(lines):
        column = _raw_column(lines[line], column)
    return line, column


def _replace_scalar_line(
    lines: list[str],
    *,
    line_number: int,
    column: int,
    value: str,
    key: str,
    newline: str,
) -> TextEdit | None:
    """Replace a simple scalar value while retaining indentation and comments."""
    original = lines[line_number]
    body = original.rstrip("\r\n")
    colon = body.find(":", column)
    if colon < 0:
        return None
    raw_value, comment = _split_inline_comment(body, colon + 1)
    if raw_value.lstrip().startswith(("|", ">")):
        return None
    replacement_body = (
        body[: colon + 1]
        + " "
        + _quote_yaml_string(value)
        + ((" " + comment) if comment else "")
    )
    ending = _line_ending(original, newline)
    return TextEdit(
        start=line_number,
        end=line_number + 1,
        replacement=replacement_body + ending,
    )


def _replace_key_and_value_line(
    lines: list[str],
    *,
    line_number: int,
    column: int,
    key: str,
    value: str,
    newline: str,
) -> TextEdit | None:
    """Replace a whole ``key: value`` pair, keeping indentation and comments."""
    original = lines[line_number]
    body = original.rstrip("\r\n")
    colon = body.find(":", column)
    if colon < 0:
        return None
    raw_value, comment = _split_inline_comment(body, colon + 1)
    if raw_value.lstrip().startswith(("|", ">")):
        return None
    replacement_body = (
        body[:column]
        + f"{key}: "
        + _quote_yaml_string(value)
        + ((" " + comment) if comment else "")
    )
    return TextEdit(
        start=line_number,
        end=line_number + 1,
        replacement=replacement_body + _line_ending(original, newline),
    )


def _replace_id_value(
    lines: list[str],
    *,
    line_number: int,
    column: int,
    value: str,
    newline: str,
) -> TextEdit | None:
    """Rewrite a simple ID, including the common ``id: |`` form."""
    edit = _replace_scalar_line(
        lines,
        line_number=line_number,
        column=column,
        value=value,
        key="id",
        newline=newline,
    )
    if edit is not None:
        return edit

    original = lines[line_number]
    body = original.rstrip("\r\n")
    colon = body.find(":", column)
    if colon < 0:
        return None
    raw_value = body[colon + 1 :].strip()
    if not raw_value.startswith(("|", ">")):
        return None

    content_line_number = line_number + 1
    if content_line_number >= len(lines):
        return _insert_before_line(
            lines,
            line_number=content_line_number,
            replacement_lines=[" " * (column + 2) + value],
            newline=newline,
        )

    content_line = lines[content_line_number]
    content_body = content_line.rstrip("\r\n")
    content_indent = len(content_body) - len(content_body.lstrip())
    if content_indent <= column:
        return _insert_before_line(
            lines,
            line_number=content_line_number,
            replacement_lines=[" " * (column + 2) + value],
            newline=newline,
        )

    # Do not guess how to rewrite a multi-line ID. The corpus uses one-line
    # block scalars here, but preserving an unusual value is safer than
    # silently changing its meaning. ``value`` is single-line by construction,
    # so only the block scalar's own source lines can answer this: a folded
    # ``id: >`` spanning two lines would otherwise keep its trailing lines and
    # fold them onto the replacement.
    for following in lines[content_line_number + 1 :]:
        following_body = following.rstrip("\r\n")
        if not following_body.strip():
            continue
        if len(following_body) - len(following_body.lstrip()) < content_indent:
            break
        return None
    replacement_body = content_body[:content_indent] + value
    return TextEdit(
        start=content_line_number,
        end=content_line_number + 1,
        replacement=replacement_body + _line_ending(content_line, newline),
    )


def _replace_mapping_key_line(
    lines: list[str],
    *,
    line_number: int,
    column: int,
    value: str,
    newline: str,
) -> TextEdit | None:
    """Replace a mapping key such as ``no label`` with a quoted label."""
    original = lines[line_number]
    body = original.rstrip("\r\n")
    colon = body.find(":", column)
    if colon < 0:
        return None
    replacement_body = (
        body[:column] + _quote_yaml_string(value) + body[colon:]
    ).rstrip()
    ending = _line_ending(original, newline)
    return TextEdit(
        start=line_number,
        end=line_number + 1,
        replacement=replacement_body + ending,
    )


def _replace_full_line(
    lines: list[str],
    *,
    line_number: int,
    replacement_lines: Iterable[str],
    newline: str,
) -> TextEdit:
    original = lines[line_number]
    ending = _line_ending(original, newline)
    replacement = newline.join(replacement_lines) + ending
    return TextEdit(line_number, line_number + 1, replacement)


def _insert_before_line(
    lines: list[str],
    *,
    line_number: int,
    replacement_lines: Iterable[str],
    newline: str,
) -> TextEdit:
    replacement = newline.join(replacement_lines) + newline
    return TextEdit(line_number, line_number, replacement)


def _field_items(document: Any) -> list[Any]:
    fields = document.get("fields") if isinstance(document, dict) else None
    if isinstance(fields, dict):
        return [fields]
    if isinstance(fields, list):
        return [item for item in fields if isinstance(item, dict)]
    return []


def _is_ea502_offending(field_item: dict[str, Any]) -> bool:
    has_no_label = _is_truthy(field_item.get("no label"))
    explicit_label = str(field_item.get("label") or "")
    inferred_label = _extract_field_label(field_item)
    label_is_blank = "label" in field_item and not explicit_label.strip()
    missing_label = not inferred_label.strip()
    return has_no_label or label_is_blank or missing_label


def _first_ea502_field(document: Any, target_lines: set[int]) -> Any | None:
    fields = _field_items(document)
    labelable_fields = [
        item
        for item in fields
        if _field_collects_user_input(item) or "no label" in item
    ]
    if len(labelable_fields) <= 1:
        return None
    # Only one field can sensibly carry the question text, so a screen whose
    # question text is already in use was labeled by an earlier run: taking a
    # second field would duplicate the label and would make repeated ``--fix``
    # runs keep eating into the fields left for human review.
    question = _normalized_question(document.get("question"))
    if question and any(
        _extract_field_label(item).strip() == question
        or str(item.get("label") or "").strip() == question
        for item in labelable_fields
    ):
        return None

    # ``_check_multifield_no_label_usage`` counts ``code`` fields towards the
    # screen's field total but never reports them, so skip them here too and
    # take the first field the checker would actually flag.
    first_field = next(
        (
            item
            for item in labelable_fields
            if "code" not in item and _is_ea502_offending(item)
        ),
        None,
    )
    if first_field is None:
        return None
    if getattr(getattr(first_field, "lc", None), "line", None) not in target_lines:
        return None
    return first_field


def _unique_id(base: str, *, reserved: set[str], used: set[str]) -> str:
    if base and base not in reserved and base not in used:
        return base
    number = 2
    while f"{base} {number}" in reserved or f"{base} {number}" in used:
        number += 1
    return f"{base} {number}"


def _document_start_matches(document: Any, target_lines: set[int]) -> bool:
    """Match checker locations that point at a document's opening line."""
    start = getattr(getattr(document, "lc", None), "line", None)
    if start is None:
        return False
    # Depending on the document's first key and surrounding ``---`` marker,
    # the checker may report the marker, the first key, or the adjacent line.
    return bool({start - 1, start, start + 1}.intersection(target_lines))


def fix_missing_question_id(
    document: Any,
    *,
    lines: list[str],
    newline: str,
    target_lines: set[int],
    reserved_ids: set[str],
    used_ids: set[str],
    edits: _EditAccumulator,
) -> None:
    """Fix EG414 by deriving a unique ID from the question text."""
    if not isinstance(document, dict):
        return

    current_id = (
        str(document.get("id")).strip() if isinstance(document.get("id"), str) else ""
    )
    question = _normalized_question(document.get("question"))
    question_key = _key_column(document, "question", lines)
    if current_id or not question or question_key is None:
        return
    if question_key[0] not in target_lines:
        return

    final_id = _unique_id(
        _normalized_id(document.get("question")), reserved=reserved_ids, used=used_ids
    )
    used_ids.add(final_id)
    id_key = _key_column(document, "id", lines)
    if id_key is not None:
        edit = _replace_id_value(
            lines,
            line_number=id_key[0],
            column=id_key[1],
            value=final_id,
            newline=newline,
        )
        if edit is None:
            raise ValueError(f"could not safely rewrite id near line {id_key[0] + 1}")
        edits.add(edit, "EG414")
        return

    question_line = lines[question_key[0]]
    indent = question_line[: len(question_line) - len(question_line.lstrip())]
    edits.add(
        _insert_before_line(
            lines,
            line_number=question_key[0],
            replacement_lines=[f"{indent}id: {_quote_yaml_string(final_id)}"],
            newline=newline,
        ),
        "EG414",
    )


def fix_duplicate_id(
    document: Any,
    *,
    lines: list[str],
    newline: str,
    target_lines: set[int],
    reserved_ids: set[str],
    used_ids: set[str],
    edits: _EditAccumulator,
) -> None:
    """Fix EG104 by suffixing each later duplicate ID once."""
    if not isinstance(document, dict):
        return

    current_id = (
        str(document.get("id")).strip() if isinstance(document.get("id"), str) else ""
    )
    if not current_id:
        return

    duplicate_is_target = current_id in used_ids and _document_start_matches(
        document, target_lines
    )
    if not duplicate_is_target:
        used_ids.add(current_id)
        return

    final_id = _unique_id(current_id, reserved=reserved_ids, used=used_ids)
    used_ids.add(final_id)
    id_key = _key_column(document, "id", lines)
    if id_key is None:
        raise ValueError("duplicate ID has no source location")
    edit = _replace_id_value(
        lines,
        line_number=id_key[0],
        column=id_key[1],
        value=final_id,
        newline=newline,
    )
    if edit is None:
        raise ValueError(f"could not safely rewrite id near line {id_key[0] + 1}")
    edits.add(edit, "EG104")


def fix_yesno_shortcut(
    document: Any,
    *,
    lines: list[str],
    newline: str,
    target_lines: set[int],
    edits: _EditAccumulator,
) -> None:
    """Fix EA510 by expanding one yes/no shortcut into an explicit field."""
    if not isinstance(document, dict) or "fields" in document:
        # Merging a shortcut with an existing fields block needs semantic
        # review; duplicate ``fields`` keys would be worse than the finding.
        return

    present = [shortcut for shortcut in SHORTCUTS if shortcut in document]
    if len(present) != 1:
        # One replacement per shortcut would write one ``fields`` key per
        # shortcut; docassemble keeps only the last, and the checker reports
        # the duplicate key. Combining them needs semantic review.
        return

    for shortcut in present:
        key_location = _key_column(document, shortcut, lines)
        value = document.get(shortcut)
        if (
            key_location is None
            or not isinstance(value, str)
            or not value.strip()
            or key_location[0] not in target_lines
        ):
            continue

        datatype = (
            "yesnomaybe" if shortcut in {"yesnomaybe", "noyesmaybe"} else "yesnoradio"
        )
        original_line = lines[key_location[0]].rstrip("\r\n")
        colon = original_line.find(":", key_location[1])
        _, comment = _split_inline_comment(original_line, colon + 1)
        key_indent = original_line[: key_location[1]]
        field_value = (
            value.strip()
            if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", value.strip())
            else _quote_yaml_string(value.strip())
        )
        fields_line = f"{key_indent}fields:"
        if comment:
            fields_line += f" {comment}"
        edits.add(
            _replace_full_line(
                lines,
                line_number=key_location[0],
                replacement_lines=[
                    fields_line,
                    f"{key_indent}  - no label: {field_value}",
                    f"{key_indent}    datatype: {datatype}",
                ],
                newline=newline,
            ),
            "EA510",
        )


def fix_missing_field_label(
    document: Any,
    *,
    lines: list[str],
    newline: str,
    target_lines: set[int],
    edits: _EditAccumulator,
) -> None:
    """Fix EA502 by labeling only the first offending input field."""
    if not isinstance(document, dict):
        return

    field_item = _first_ea502_field(document, target_lines)
    if field_item is None:
        return
    question = _normalized_question(document.get("question"))
    if not question:
        return

    raw_question = document.get("question")
    needs_block = _question_needs_block_label(raw_question)

    first_key = next(iter(field_item), None)
    if first_key == "":
        key_location = _key_column(field_item, first_key, lines)
        if key_location is None:
            return
        edit = _shorthand_label_edit(
            lines,
            key_location=key_location,
            field_item=field_item,
            key=first_key,
            question=question,
            raw_question=raw_question,
            needs_block=needs_block,
            newline=newline,
        )
        if edit is not None:
            edits.add(edit, "EA502")
        return

    if "no label" in field_item:
        key_location = _key_column(field_item, "no label", lines)
        if key_location is None:
            return
        no_label_value = field_item.get("no label")
        if isinstance(no_label_value, str) and no_label_value.strip():
            # ``no label: some_variable`` names the field: turning the key
            # into the label keeps the variable where it is.
            edit = _shorthand_label_edit(
                lines,
                key_location=key_location,
                field_item=field_item,
                key="no label",
                question=question,
                raw_question=raw_question,
                needs_block=needs_block,
                newline=newline,
            )
        else:
            # ``no label: true`` (or a bare ``no label:``) is a modifier, not
            # a variable name. Rewriting the key would make the boolean the
            # field's value; replace the modifier with the missing label
            # instead, which is the change the rule is asking for.
            edit = (
                _block_label_edit(
                    lines,
                    line_number=key_location[0],
                    column=key_location[1],
                    question=raw_question,
                    variable=None,
                    newline=newline,
                )
                if needs_block
                else _replace_key_and_value_line(
                    lines,
                    line_number=key_location[0],
                    column=key_location[1],
                    key="label",
                    value=question,
                    newline=newline,
                )
            )
        if edit is not None:
            edits.add(edit, "EA502")
        return

    if "label" in field_item:
        key_location = _key_column(field_item, "label", lines)
        if key_location is None:
            return
        if needs_block:
            edit = _block_label_edit(
                lines,
                line_number=key_location[0],
                column=key_location[1],
                question=raw_question,
                variable=None,
                newline=newline,
            )
            if edit is not None:
                edits.add(edit, "EA502")
            return
        edit = _replace_scalar_line(
            lines,
            line_number=key_location[0],
            column=key_location[1],
            value=question,
            key="label",
            newline=newline,
        )
        if edit is not None:
            edits.add(edit, "EA502")
        return

    if first_key is None or needs_block:
        # A sibling ``label:`` would have to be a block scalar inserted next to
        # a key whose own layout we have not inspected; leave it for a human.
        return
    key_location = _key_column(field_item, first_key, lines)
    if key_location is None:
        return
    # The key column sits past any ``- `` sequence marker, so copying the
    # prefix verbatim would start a new list item instead of adding a sibling
    # property. Blank out the marker but keep the original whitespace bytes.
    field_line = lines[key_location[0]]
    indent = re.sub(r"\S", " ", field_line[: key_location[1]])
    edits.add(
        _insert_before_line(
            lines,
            line_number=key_location[0] + 1,
            replacement_lines=[f"{indent}label: {_quote_yaml_string(question)}"],
            newline=newline,
        ),
        "EA502",
    )


def _all_findings(
    text: str, path: Path, options: FixOptions | None = None
) -> list[Finding]:
    options = options or FixOptions()
    return [
        finding
        for finding in find_errors_from_string(
            text,
            input_file=str(path),
            lint_mode=options.lint_mode,
            runtime_options=options.runtime_options,
        )
        if not _finding_matches_suppression(finding, options.suppressed_codes)
    ]


def _all_counts(
    text: str, path: Path, options: FixOptions | None = None
) -> Counter[str]:
    return Counter(finding.code for finding in _all_findings(text, path, options))


def _shorthand_label_edit(
    lines: list[str],
    *,
    key_location: tuple[int, int],
    field_item: dict[str, Any],
    key: str,
    question: str,
    raw_question: Any,
    needs_block: bool,
    newline: str,
) -> TextEdit | None:
    """Label a ``<key>: variable`` field, in block form when Mako requires it."""
    if not needs_block:
        return _replace_mapping_key_line(
            lines,
            line_number=key_location[0],
            column=key_location[1],
            value=question,
            newline=newline,
        )
    variable = field_item.get(key)
    if not isinstance(variable, str) or not variable.strip():
        return None
    return _block_label_edit(
        lines,
        line_number=key_location[0],
        column=key_location[1],
        question=raw_question,
        variable=variable.strip(),
        newline=newline,
    )


def _target_findings(
    text: str, path: Path, options: FixOptions | None = None
) -> list[Finding]:
    return [
        finding
        for finding in _all_findings(text, path, options)
        if finding.code in TARGET_CODES
    ]


def _target_counts(
    text: str, path: Path, options: FixOptions | None = None
) -> Counter[str]:
    return Counter(finding.code for finding in _target_findings(text, path, options))


def plan_file(path: Path, options: FixOptions | None = None) -> FilePlan:
    options = options or FixOptions()
    plan = FilePlan(path=path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        plan.skipped_reason = f"could not read file: {exc}"
        return plan

    documents, parse_error = _load_documents(text)
    if documents is None:
        plan.skipped_reason = f"YAML parse failed: {parse_error}"
        return plan

    target_findings = _target_findings(text, path, options)
    target_lines_by_code: dict[str, set[int]] = defaultdict(set)
    for finding in target_findings:
        if finding.line_number is not None:
            target_lines_by_code[finding.code].add(finding.line_number - 1)

    lines = text.splitlines(keepends=True)
    newline = _newline_for(text)
    edits = _EditAccumulator()

    # Preserve all original IDs whenever possible, then generate IDs for
    # missing-question blocks and suffix later duplicate IDs.
    reserved_ids = {
        str(document.get("id")).strip()
        for document in documents
        if isinstance(document, dict)
        and isinstance(document.get("id"), str)
        and str(document.get("id")).strip()
    }
    used_ids: set[str] = set()

    try:
        for document in documents:
            fix_missing_question_id(
                document,
                lines=lines,
                newline=newline,
                target_lines=target_lines_by_code["EG414"],
                reserved_ids=reserved_ids,
                used_ids=used_ids,
                edits=edits,
            )
            fix_duplicate_id(
                document,
                lines=lines,
                newline=newline,
                target_lines=target_lines_by_code["EG104"],
                reserved_ids=reserved_ids,
                used_ids=used_ids,
                edits=edits,
            )
            fix_yesno_shortcut(
                document,
                lines=lines,
                newline=newline,
                target_lines=target_lines_by_code["EA510"],
                edits=edits,
            )
            fix_missing_field_label(
                document,
                lines=lines,
                newline=newline,
                target_lines=target_lines_by_code["EA502"],
                edits=edits,
            )
    except ValueError as exc:
        plan.skipped_reason = str(exc)
        return plan

    if not edits.edits:
        return plan

    # Apply bottom-up so line locations from ruamel remain valid.
    new_lines = list(lines)
    for edit in sorted(
        edits.edits, key=lambda item: (item.start, item.end), reverse=True
    ):
        new_lines[edit.start : edit.end] = edit.replacement.splitlines(keepends=True)
    candidate = "".join(new_lines)

    # Never write a candidate that no longer parses.
    _, candidate_parse_error = _load_documents(candidate)
    if candidate_parse_error:
        plan.validation_error = (
            f"candidate YAML does not parse: {candidate_parse_error}"
        )
        return plan

    # Compare every rule, not just the four the fixer targets. The loader
    # above tolerates duplicate keys and ignores rules outside TARGET_CODES,
    # so a botched edit can round-trip cleanly here while the checker reports
    # a brand new error against the file the user is left with.
    original_counts = _all_counts(text, path, options)
    candidate_counts = _all_counts(candidate, path, options)
    introduced = sorted(
        code
        for code in candidate_counts
        if candidate_counts[code] > original_counts[code]
    )
    if introduced:
        plan.validation_error = "candidate introduces new findings: " + ", ".join(
            f"{code} ({original_counts[code]} -> {candidate_counts[code]})"
            for code in introduced
        )
        return plan

    # The three deterministic families must be gone after the edit; EA502 may
    # intentionally remain when a screen had several unlabeled fields.
    for code in ("EG414", "EA510", "EG104"):
        if candidate_counts[code] > 0:
            plan.validation_error = (
                f"candidate still has {candidate_counts[code]} {code} finding(s)"
            )
            return plan

    # An edit that removes nothing is not a fix, however well it parses.
    for code, applied in sorted(edits.counts.items()):
        if candidate_counts[code] >= original_counts[code]:
            plan.validation_error = (
                f"candidate applied {applied} {code} edit(s) without reducing "
                f"{code} findings ({original_counts[code]} -> "
                f"{candidate_counts[code]})"
            )
            return plan

    plan.edits = edits.edits
    plan.counts = dict(edits.counts)
    return plan


def apply_plan(plan: FilePlan, *, write: bool) -> None:
    if not plan.changed or not write:
        return
    text = plan.path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for edit in sorted(
        plan.edits, key=lambda item: (item.start, item.end), reverse=True
    ):
        lines[edit.start : edit.end] = edit.replacement.splitlines(keepends=True)
    plan.path.write_text("".join(lines), encoding="utf-8")


def run(
    paths: list[Path],
    *,
    write: bool,
    include_default_ignores: bool,
    options: FixOptions | None = None,
) -> dict[str, Any]:
    options = options or FixOptions()
    yaml_files = _collect_yaml_files(
        paths, include_default_ignores=include_default_ignores
    )
    plans = [plan_file(path, options) for path in yaml_files]
    for plan in plans:
        apply_plan(plan, write=write)

    counts: Counter[str] = Counter()
    for plan in plans:
        counts.update(plan.counts)
    result = {
        "mode": "write" if write else "dry-run",
        "yaml_files": len(yaml_files),
        "files_with_changes": sum(plan.changed for plan in plans),
        "files_skipped": sum(plan.skipped_reason is not None for plan in plans),
        "files_rejected": sum(plan.validation_error is not None for plan in plans),
        "changes_by_code": dict(sorted(counts.items())),
        "plans": [
            {
                "file": str(plan.path),
                "changes": plan.counts,
                "skipped_reason": plan.skipped_reason,
                "validation_error": plan.validation_error,
            }
            for plan in plans
            if plan.changed or plan.skipped_reason or plan.validation_error
        ],
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="YAML files or directories to scan recursively",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write safe plans to disk (default: dry run)",
    )
    parser.add_argument(
        "--check-all",
        action="store_true",
        help="Include default-ignored directories during recursive search",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write the run summary as JSON",
    )
    args = parser.parse_args(argv)
    result = run(
        args.files,
        write=args.write,
        include_default_ignores=not args.check_all,
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"Mode: {result['mode']}")
    print(f"YAML files scanned: {result['yaml_files']}")
    print(f"Files with changes: {result['files_with_changes']}")
    print(f"Files skipped: {result['files_skipped']}")
    print(f"Files rejected by validation: {result['files_rejected']}")
    print(f"Changes by rule: {result['changes_by_code']}")
    for plan in result["plans"]:
        if plan["skipped_reason"]:
            print(f"SKIP {plan['file']}: {plan['skipped_reason']}", file=sys.stderr)
        if plan["validation_error"]:
            print(
                f"REJECT {plan['file']}: {plan['validation_error']}",
                file=sys.stderr,
            )
    return 1 if result["files_skipped"] or result["files_rejected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
