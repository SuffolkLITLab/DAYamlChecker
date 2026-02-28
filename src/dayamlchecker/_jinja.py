"""
Jinja2 detection, header validation, and pre-processing utilities for
docassemble YAML files.

Per docassemble documentation, Jinja2 template processing must be explicitly
enabled by placing ``# use jinja`` as the very first line of a YAML file.
Files that contain Jinja syntax without that header are considered invalid.

Reference: https://docassemble.org/docs/interviews.html#jinja2
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import jinja2

if TYPE_CHECKING:
    pass

__all__ = [
    "JinjaWithoutHeaderError",
    "_contains_jinja_syntax",
    "_has_jinja_header",
    "preprocess_jinja",
]


class JinjaWithoutHeaderError(Exception):
    """Raised when a YAML file contains Jinja syntax but lacks the '# use jinja' header.

    Per docassemble documentation, Jinja2 processing must be explicitly enabled by
    placing ``# use jinja`` as the very first line of the file.  A file that contains
    Jinja constructs without that header is considered invalid.
    """


_JINJA_SYNTAX_RE = re.compile(
    r"({{.*?}}|{%-?.*?-?%}|{#.*?#})",
    re.DOTALL,
)


def _contains_jinja_syntax(content: str) -> bool:
    """Return True if *content* contains any Jinja template syntax.

    Looks for properly delimited Jinja constructs (``{{ ... }}``, ``{% ... %}``,
    ``{# ... #}``) rather than simple substring checks to avoid false positives
    from Python dicts or other curly-brace usage.
    """
    return _JINJA_SYNTAX_RE.search(content) is not None


def _has_jinja_header(content: str) -> bool:
    """Return True if the first line of *content* is exactly ``# use jinja``.

    Per docassemble documentation this header must appear on the very first line
    of the file (written exactly this way) to enable Jinja2 template processing.
    Leading whitespace before the ``#`` disqualifies the line.
    """
    first_line = content.split("\n", 1)[0].rstrip()
    return first_line == "# use jinja"


class _SilentUndefined(jinja2.Undefined):
    """Undefined template variables render as empty string instead of raising.

    Docassemble interview templates reference runtime variables (user answers,
    DA objects) that are unavailable during static analysis.  This class makes
    every undefined reference silently produce an empty value so that the
    rendered YAML can still be structurally validated.
    """

    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter([])

    def __len__(self) -> int:
        return 0

    # Allow arbitrary attribute / item / call chaining without raising.
    def __getattr__(self, name: str) -> "_SilentUndefined":
        # Guard: don't swallow Python's own dunder / private lookups.
        if name.startswith("_"):
            raise AttributeError(name)
        return _SilentUndefined()

    def __getitem__(self, key: object) -> "_SilentUndefined":  # type: ignore[override]
        # jinja2.Undefined declares __getitem__ as returning Never (it always
        # raises UndefinedError). We intentionally return a _SilentUndefined
        # instead so that subscript access on an undefined value chains
        # silently rather than blowing up during static analysis.
        return _SilentUndefined()

    def __call__(self, *args: object, **kwargs: object) -> "_SilentUndefined":  # type: ignore[override]
        # Same reasoning as __getitem__: jinja2.Undefined declares __call__
        # as returning Never, but we return _SilentUndefined so that calling
        # an undefined value (e.g. {{ some_macro() }}) produces an empty
        # value instead of raising during static analysis.
        return _SilentUndefined()


def preprocess_jinja(content: str) -> tuple[str, list[str]]:
    """Render *content* as a Jinja2 template and return ``(rendered, errors)``.

    Uses :class:`_SilentUndefined` so that template variables unavailable at
    static-analysis time produce empty strings rather than raising errors.
    Jinja2 *syntax* errors are captured and returned in *errors*; in that case
    *rendered* equals *content* unchanged so the caller can still report the
    problem against the original source.

    The ``# use jinja`` header line (if present) is passed through Jinja2
    unchanged — it is a plain YAML comment, not a Jinja2 construct.

    Args:
        content: Raw file content, including the ``# use jinja`` header.

    Returns:
        Tuple of ``(rendered_text, error_messages)``.  A non-empty
        *error_messages* list means the template had render errors.
    """
    env = jinja2.Environment(
        undefined=_SilentUndefined,
        keep_trailing_newline=True,
    )

    try:
        template = env.from_string(content)
    except jinja2.exceptions.TemplateSyntaxError as ex:
        return content, [f"Jinja2 syntax error at line {ex.lineno}: {ex.message}"]

    try:
        rendered = template.render()
    except jinja2.exceptions.TemplateError as ex:
        return content, [f"Jinja2 template error: {ex}"]

    return rendered, []
