"""
Docassemble YAML code block formatter.

Formats Python code blocks in docassemble YAML files using Black,
then converts 4-space indentation to 2-space indentation to match
docassemble conventions.

Supported keys:
- code: Main code blocks
- validation code: Question field validation code

Usage:
    python -m dayamlchecker.code_formatter path/to/interview.yml
"""

from __future__ import annotations

import re
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import black
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

__all__ = [
    "format_yaml_file",
    "format_yaml_string",
    "format_python_code",
    "FormatterConfig",
]


@dataclass
class FormatterConfig:
    """Configuration for the code formatter."""

    # Keys that contain Python code to format
    python_keys: set[str] = field(default_factory=lambda: {"code", "validation code"})

    # Black configuration
    black_line_length: int = 88
    black_target_versions: set[black.TargetVersion] = field(default_factory=set)

    # Indentation conversion
    convert_indent_4_to_2: bool = True

    # If True, folded scalars (">") become literal ("|") after formatting
    prefer_literal_blocks: bool = True

    # Whether to preserve trailing whitespace in formatted blocks
    strip_trailing_whitespace: bool = True


def _normalize_newlines(text: str) -> str:
    """Normalize all newline variants to Unix-style LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _strip_common_indent(lines: list[str]) -> tuple[list[str], int]:
    """
    Remove common leading whitespace from non-empty lines.

    Returns:
        Tuple of (dedented lines, number of spaces removed)
    """
    indents = []
    for line in lines:
        if line.strip():  # Skip empty/whitespace-only lines
            match = re.match(r"^( *)", line)
            if match:
                indents.append(len(match.group(1)))

    if not indents:
        return lines, 0

    min_indent = min(indents)
    dedented = []
    for line in lines:
        if len(line) >= min_indent:
            dedented.append(line[min_indent:])
        else:
            dedented.append(line.lstrip() if line.strip() else "")
    return dedented, min_indent


def _convert_indent_4_to_2(text: str) -> str:
    """
    Convert leading 4-space indentation to 2-space indentation.

    Only converts lines where the leading whitespace is a multiple of 4 spaces.
    This preserves alignment for continuation lines and special formatting.
    """
    result_lines = []
    for line in text.splitlines(keepends=True):
        # Count leading spaces
        stripped = line.lstrip(" ")
        leading_count = len(line) - len(stripped)

        if leading_count > 0 and leading_count % 4 == 0:
            new_indent = " " * (leading_count // 2)
            result_lines.append(new_indent + stripped)
        else:
            result_lines.append(line)

    return "".join(result_lines)


def _reindent(text: str, indent: int) -> str:
    """Re-apply indentation to non-empty lines."""
    if indent <= 0:
        return text

    padding = " " * indent
    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        if line.strip():
            result.append(padding + line)
        else:
            result.append(line)
    return "".join(result)


def format_python_code(
    code: str,
    config: FormatterConfig | None = None,
    original_indent: int = 0,
) -> str:
    """
    Format Python code using Black with 4-to-2 space indentation conversion.

    Args:
        code: The Python code to format
        config: Formatter configuration (uses defaults if None)
        original_indent: Original indentation to restore after formatting

    Returns:
        Formatted Python code

    Raises:
        black.InvalidInput: If the code cannot be parsed as Python
    """
    if config is None:
        config = FormatterConfig()

    # Normalize newlines
    code = _normalize_newlines(code)

    # Strip common indentation
    lines = code.splitlines(keepends=True)
    dedented_lines, removed_indent = _strip_common_indent(lines)
    dedented_text = "".join(dedented_lines)

    # Ensure trailing newline for Black
    if not dedented_text.endswith("\n"):
        dedented_text += "\n"

    # Format with Black
    mode = black.Mode(
        line_length=config.black_line_length,
        target_versions=config.black_target_versions,
    )
    try:
        formatted = black.format_file_contents(dedented_text, fast=False, mode=mode)
    except black.NothingChanged:
        # Code is already formatted
        formatted = dedented_text

    # Convert 4-space to 2-space indentation
    if config.convert_indent_4_to_2:
        formatted = _convert_indent_4_to_2(formatted)

    # Strip trailing whitespace from each line if configured
    if config.strip_trailing_whitespace:
        formatted = "\n".join(line.rstrip() for line in formatted.splitlines())
        if formatted and not formatted.endswith("\n"):
            formatted += "\n"

    # Restore original indentation from the source code itself
    if removed_indent > 0:
        formatted = _reindent(formatted, removed_indent)

    # Restore external indentation (e.g. YAML block scalar indentation)
    if original_indent > 0:
        formatted = _reindent(formatted, original_indent)

    return formatted


def _count_leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_block_body_span(lines: list[str], header_line: int) -> tuple[int, int, int]:
    """Return (body_start, body_end, body_first_indent) for a block scalar whose
    header is at header_line. Lines is the full document splitlines(keepends=True).

    The body is considered to include subsequent lines with indentation strictly
    greater than the header indentation. Returns inclusive indices for start/end.
    If there is no body, returns (header_line+1, header_line, 0).
    """
    header_indent = _count_leading_spaces(lines[header_line])
    start = header_line + 1
    if start >= len(lines):
        return start, start - 1, 0

    # Determine first non-empty body line to get the in-block indentation,
    # and continue until the first non-empty dedent.
    i = start
    first_body_indent: int | None = None
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "":
            # Blank lines are part of block scalars regardless of indentation.
            i += 1
            continue

        leading = _count_leading_spaces(ln)

        if first_body_indent is None:
            if leading <= header_indent:
                # No body content and dedented line: empty block body.
                break
            first_body_indent = leading
            i += 1
            continue

        if leading < first_body_indent:
            # Dedent below block content indentation means block ended.
            break

        i += 1

    end = i - 1
    if first_body_indent is None:
        first_body_indent = header_indent + 2

    return start, end, first_body_indent


def _collect_text_replacements_for_doc(
    doc: Any, lines: list[str], config: FormatterConfig, path: tuple[str, ...] = ()
) -> list[tuple[int, int, str, tuple[str, ...]]]:
    """Walk a CommentedMap/CommentedSeq and collect textual replacements for
    block scalar bodies that need formatting.

    Returns a list of tuples: (body_start_line, body_end_line, new_text, path)
    where line numbers are 0-based indices into lines (inclusive end).
    """
    replacements: list[tuple[int, int, str, tuple[str, ...]]] = []

    if isinstance(doc, CommentedMap):
        for key, value in list(doc.items()):
            key_str = str(key)
            current_path = path + (key_str,)

            # Only consider keys we care about and plain strings
            if (
                key_str in config.python_keys
                and isinstance(value, str)
                and hasattr(doc.lc, "key")
            ):
                try:
                    key_line, _ = doc.lc.key(key)
                except Exception:
                    # fallback: can't locate position -> skip textual replace
                    key_line = None

                if key_line is not None:
                    # Determine the body span in the original text
                    body_start, body_end, body_indent = _find_block_body_span(
                        lines, key_line
                    )

                    if body_end >= body_start:
                        # Format using the detected body indent so we reinsert with the
                        # same indentation level
                        formatted = format_python_code(
                            value, config, original_indent=body_indent
                        )

                        # Normalize newlines for comparison
                        if _normalize_newlines(formatted) != _normalize_newlines(value):
                            replacements.append(
                                (body_start, body_end, formatted, current_path)
                            )
            else:
                # Recurse into nested structures
                if isinstance(value, (CommentedMap, CommentedSeq)):
                    replacements.extend(
                        _collect_text_replacements_for_doc(
                            value, lines, config, current_path
                        )
                    )

    elif isinstance(doc, CommentedSeq):
        for idx, item in enumerate(doc):
            replacements.extend(
                _collect_text_replacements_for_doc(
                    item, lines, config, path + (str(idx),)
                )
            )

    return replacements


def format_yaml_string(
    yaml_content: str,
    config: FormatterConfig | None = None,
) -> tuple[str, bool]:
    """
    Format Python code blocks in a YAML string.

    This implementation prefers to perform in-place textual replacements for
    block scalar bodies so that unrelated YAML formatting (booleans, sequence
    indentation, comments) is preserved exactly.

    Args:
        yaml_content: The YAML content as a string
        config: Formatter configuration (uses defaults if None)

    Returns:
        Tuple of (formatted YAML string, whether any changes were made)
    """
    if config is None:
        config = FormatterConfig()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # Prevent line wrapping in strings
    # Use ruamel's parser to obtain position metadata; we'll replace text

    # Load as a stream to handle multi-document YAML
    documents = list(yaml.load_all(yaml_content))

    lines = yaml_content.splitlines(keepends=True)
    all_replacements: list[tuple[int, int, str, tuple[str, ...]]] = []

    for doc in documents:
        if doc is None:
            continue
        repls = _collect_text_replacements_for_doc(doc, lines, config)
        all_replacements.extend(repls)

    if all_replacements:
        # Apply replacements from bottom to top so indices don't shift
        all_replacements.sort(key=lambda t: t[0], reverse=True)
        for start, end, new_text, _ in all_replacements:
            new_lines = new_text.splitlines(keepends=True)

            # Keep parity with original replacement slice: if the original body
            # had no trailing newline on its final line, avoid introducing one.
            if end >= start and not lines[end].endswith("\n") and new_lines:
                new_lines[-1] = new_lines[-1].rstrip("\n")

            lines[start : end + 1] = new_lines

    return "".join(lines), bool(all_replacements)


def format_yaml_file(
    file_path: str | Path,
    config: FormatterConfig | None = None,
    write: bool = True,
) -> tuple[str, bool]:
    """
    Format Python code blocks in a YAML file.

    Args:
        file_path: Path to the YAML file
        config: Formatter configuration (uses defaults if None)
        write: Whether to write changes back to the file

    Returns:
        Tuple of (formatted content, whether any changes were made)
    """
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")

    formatted, changed = format_yaml_string(content, config)

    if changed and write:
        path.write_text(formatted, encoding="utf-8")

    return formatted, changed


def _collect_yaml_files(
    paths: list[Path],
    check_all: bool = False,
    include_default_ignores: bool | None = None,
) -> list[Path]:
    """
    Expand paths to a list of YAML files.

    - Files are included if they have .yml or .yaml extension
    - Directories are recursively searched for YAML files
    """

    def _is_default_ignored_dir(dirname: str) -> bool:
        return (
            dirname.startswith(".git")
            or dirname.startswith(".github")
            or dirname.startswith(".venv")
            or dirname == "sources"
        )

    if include_default_ignores is None:
        include_default_ignores = not check_all

    yaml_files: list[Path] = []
    for path in paths:
        if path.is_dir():
            # Recursively find all YAML files, pruning ignored directories
            for root, dirnames, filenames in os.walk(path, topdown=True):
                if include_default_ignores and _is_default_ignored_dir(Path(root).name):
                    dirnames[:] = []
                    continue
                if include_default_ignores:
                    dirnames[:] = [
                        dirname
                        for dirname in dirnames
                        if not _is_default_ignored_dir(dirname)
                    ]
                root_path = Path(root)
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


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Format Python code blocks in docassemble YAML files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s interview.yml
    %(prog)s --check interview.yml
    %(prog)s --line-length 79 interview.yml
    %(prog)s *.yml
    %(prog)s .                          # Format all YAML in current directory
    %(prog)s docassemble/MyRepo/        # Format all YAML in subdirectory
        """,
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="YAML files or directories to format (directories are searched recursively)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files would be reformatted (don't write changes)",
    )
    parser.add_argument(
        "--line-length",
        type=int,
        default=88,
        help="Black line length (default: 88)",
    )
    parser.add_argument(
        "--no-indent-conversion",
        action="store_true",
        help="Disable 4-to-2 space indentation conversion",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only output errors",
    )
    parser.add_argument(
        "--check-all",
        action="store_true",
        help=(
            "Do not ignore default directories during recursive search "
            "(.git*, .github*, sources)"
        ),
    )

    args = parser.parse_args()

    config = FormatterConfig(
        black_line_length=args.line_length,
        convert_indent_4_to_2=not args.no_indent_conversion,
    )

    # Collect all YAML files from paths (handles directories recursively)
    yaml_files = _collect_yaml_files(args.files, check_all=args.check_all)
    if not yaml_files:
        print("No YAML files found.", file=sys.stderr)
        return 1

    exit_code = 0
    files_changed = 0
    files_unchanged = 0
    files_error = 0

    for file_path in yaml_files:
        if not file_path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            files_error += 1
            exit_code = 1
            continue

        try:
            _, changed = format_yaml_file(
                file_path,
                config=config,
                write=not args.check,
            )

            if changed:
                files_changed += 1
                if args.check:
                    print(f"Would reformat: {file_path}")
                    exit_code = 1
                elif not args.quiet:
                    print(f"Reformatted: {file_path}")
            else:
                files_unchanged += 1
                if not args.quiet:
                    print(f"Unchanged: {file_path}")

        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)
            files_error += 1
            exit_code = 1

    if not args.quiet:
        total = files_changed + files_unchanged + files_error
        print()
        print(
            f"Summary: {files_changed} reformatted, {files_unchanged} unchanged, {files_error} errors ({total} total)"
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
