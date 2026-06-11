from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
import html
import importlib.resources
import json
import os
import re
from typing import Any, Iterable, Optional

from dayamlchecker.accessibility import (
    _absolute_line_number,
    _extract_field_label,
    _extract_field_variable,
    _find_top_level_key_line,
    _iter_fields,
)
from dayamlchecker.messages import Finding, FindingDraft, MessageId, draft, make_finding
import requests
from ruamel.yaml import YAML

VISIBLE_TEXT_KEYS = ("question", "subquestion", "under", "help", "note", "html")
_OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
_OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
_OPENAI_MODEL_ENV = "OPENAI_MODEL"
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_MAKO_EXPR_RE = re.compile(r"\$\{.*?\}", re.DOTALL)
_MAKO_BLOCK_RE = re.compile(r"<%[\s\S]*?%>")
_MAKO_CONTROL_RE = re.compile(r"(?m)^\s*%.*$")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_CODE_RE = re.compile(r"`([^`]+)`")
_FILE_TAG_RE = re.compile(
    r"\[FILE\s+([^,\]]+)(?:\s*,\s*([^,\]]+))?(?:\s*,\s*([^\]]+))?\]",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")
_WORD_RE = re.compile(r"\b\w+\b")
_COMPOUND_QUESTION_RE = re.compile(
    r"\b(?:and|or)\s+"
    r"(?:who|what|when|where|why|how|do|does|did|is|are|am|was|were|"
    r"can|could|will|would|should|have|has|had)\b",
    re.IGNORECASE,
)
_CONTRACTION_RE = re.compile(
    r"\b(?:can't|won't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't|"
    r"haven't|hasn't|hadn't|couldn't|shouldn't|wouldn't|mustn't|"
    r"I'm|you're|we're|they're|it's|that's|there's|what's|who's|"
    r"I'll|you'll|we'll|they'll|I'll|I'd|you'd|we'd|they'd)\b",
    re.IGNORECASE,
)
_SLASH_ALTERNATIVE_RE = re.compile(r"\b[A-Za-z]+/[A-Za-z]+(?:/[A-Za-z]+)*\b")
_ALLOWED_SLASH_ALTERNATIVES = frozenset(
    {
        "she/her/hers",
        "she/her",
        "he/him/his",
        "he/him",
        "they/them/theirs",
        "they/them",
        "ze/zir/zirs",
        "ze/zir",
        "n/a",
    }
)
_FIELD_LABEL_INSTRUCTION_VERB_RE = re.compile(
    r"^(?:please\s+)?(?:enter|write)\b|^(?:please\s+)?list\s+(?!of\b)",
    re.IGNORECASE,
)
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\blorem ipsum\b", re.IGNORECASE),
    re.compile(r"\btodo\b", re.IGNORECASE),
    re.compile(r"\btbd\b", re.IGNORECASE),
    re.compile(r"\bto be determined\b", re.IGNORECASE),
    re.compile(r"\bcoming soon\b", re.IGNORECASE),
    re.compile(r"\[insert[^\]]*\]", re.IGNORECASE),
    re.compile(r"\byour text here\b", re.IGNORECASE),
)
_USER_FACING_CODE_CALLS = frozenset(
    {"action_button_html", "action_menu_item", "validation_error", "word"}
)
_USER_FACING_CODE_NAME_PARTS = frozenset(
    {
        "body",
        "button",
        "caption",
        "error",
        "footer",
        "header",
        "heading",
        "help",
        "hint",
        "instruction",
        "instructions",
        "intro",
        "label",
        "menu",
        "message",
        "note",
        "prompt",
        "question",
        "subject",
        "subquestion",
        "title",
        "warning",
    }
)
_USER_FACING_CODE_EXACT_NAMES = frozenset({"interview_short_title"})


@dataclass(frozen=True)
class ParsedInterviewDocument:
    doc: dict[str, Any]
    source_code: str
    document_start_line: int
    index: int

    @property
    def screen_id(self) -> str:
        for key in ("id", "event"):
            value = _stringify(self.doc.get(key)).strip()
            if value:
                return value
        return f"block-{self.index}"

    def line_for_key(self, key: str) -> int:
        key_line = _find_top_level_key_line(self.source_code, key)
        if key_line is not None:
            return _absolute_line_number(
                self.source_code,
                self.document_start_line,
                key_line,
                f"{key}:",
            )
        return self.document_start_line + self.doc.get("__line__", 1) - 1

    def line_for_field(self, field: dict[str, Any]) -> int:
        return (
            self.document_start_line
            + field.get("__line__", self.doc.get("__line__", 1))
            - 1
        )

    def default_line(self) -> int:
        question = _stringify(self.doc.get("question")).strip()
        if question:
            return self.line_for_key("question")
        return self.document_start_line + self.doc.get("__line__", 1) - 1


@dataclass(frozen=True)
class TextEntry:
    location: str
    text: str
    line_number: int
    screen_id: str


@dataclass(frozen=True)
class StyleLintOptions:
    enabled: bool = False
    include_llm: bool = False
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None

    def llm_enabled(self) -> bool:
        return self.include_llm

    def resolved_openai_base_url(self) -> str:
        return (
            _stringify(self.openai_base_url).strip()
            or os.getenv(_OPENAI_BASE_URL_ENV, "").strip()
            or _DEFAULT_OPENAI_BASE_URL
        )

    def resolved_openai_api_key(self) -> str:
        return (
            _stringify(self.openai_api_key).strip()
            or os.getenv(_OPENAI_API_KEY_ENV, "").strip()
        )

    def resolved_openai_model(self) -> str:
        return (
            _stringify(self.openai_model).strip()
            or os.getenv(_OPENAI_MODEL_ENV, "").strip()
            or _DEFAULT_OPENAI_MODEL
        )


def _style_draft(
    message_id: str,
    *,
    line_number: int = 1,
    screen_id: str | None = None,
    **context: Any,
) -> FindingDraft:
    payload = dict(context)
    if screen_id:
        payload["screen_id"] = screen_id
    return draft(message_id, line_number=line_number, **payload)


def find_style_findings(
    *,
    docs: Iterable[ParsedInterviewDocument],
    input_file: str | None,
    options: Optional[StyleLintOptions] = None,
) -> list[Finding]:
    resolved_options = options or StyleLintOptions()
    parsed_docs = list(docs)
    deterministic: list[Finding] = []

    for check in (
        _check_choices_without_invariant_values,
        _check_hardcoded_strings_in_code,
        _check_ternary_conditional_text,
        _check_conditional_sentence_fragments,
        _check_subquestion_h1,
        _check_language_en_flag,
        _check_empty_screen_title,
        _check_placeholder_language,
        _check_plain_language_replacements,
        _check_contractions,
        _check_slash_alternatives,
        _check_variable_conventions,
        _check_long_sentences,
        _check_compound_questions,
        _check_overlong_labels,
        _check_field_label_instruction_verbs,
        _check_title_case_labels,
        _check_other_choice_position,
        _check_language_fields,
        _check_pronoun_and_gender_fields,
        _check_too_many_fields,
        _check_wall_of_text,
        _check_question_level_help,
        _check_missing_help_on_complex_screens,
        _check_exit_criteria_and_screen,
        _check_theme_usage,
        _check_review_screen_editability,
        _check_prefer_person_objects,
    ):
        deterministic.extend(
            finding.to_finding(file_name=input_file or "<string input>")
            for finding in check(parsed_docs)
        )

    if not resolved_options.llm_enabled():
        return _dedupe_findings(deterministic)

    llm_api_key = resolved_options.resolved_openai_api_key()
    if not llm_api_key:
        deterministic.append(
            make_finding(
                MessageId.STYLE_LLM_CONFIGURATION_ERROR,
                file_name=input_file,
                line_number=parsed_docs[0].default_line() if parsed_docs else 1,
                screen_id=parsed_docs[0].screen_id if parsed_docs else "",
                detail=(
                    "style LLM checks require an API key via "
                    "--openai-api-key or OPENAI_API_KEY"
                ),
            )
        )
        return _dedupe_findings(deterministic)

    deterministic.extend(
        _run_llm_rules(
            parsed_docs=parsed_docs,
            input_file=input_file,
            options=resolved_options,
        )
    )
    return _dedupe_findings(deterministic)


# Translatability checks
def _check_choices_without_invariant_values(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []

    def has_noninvariant_choices(choices: Any) -> bool:
        if not isinstance(choices, list):
            return False
        for item in choices:
            if isinstance(item, str) and ": " not in item:
                return True
            if not isinstance(item, dict):
                continue
            if len(item) == 1 and "label" not in item and "value" not in item:
                continue
            if "label" in item and "value" not in item:
                return True
        return False

    for parsed_doc in docs:
        for key in ("choices", "dropdown", "buttons"):
            value = parsed_doc.doc.get(key)
            if not has_noninvariant_choices(value):
                continue
            findings.append(
                _style_draft(
                    MessageId.TRANSLATABILITY_CHOICES_WITHOUT_INVARIANT_VALUES,
                    line_number=parsed_doc.line_for_key(key),
                    screen_id=parsed_doc.screen_id,
                    origin=key,
                    snippet=_shorten(value),
                )
            )
        for field in _iter_fields(parsed_doc.doc):
            choices = field.get("choices")
            if not has_noninvariant_choices(choices):
                continue
            findings.append(
                _style_draft(
                    MessageId.TRANSLATABILITY_CHOICES_WITHOUT_INVARIANT_VALUES,
                    line_number=parsed_doc.line_for_field(field),
                    screen_id=parsed_doc.screen_id,
                    origin="field choices",
                    snippet=_shorten(choices),
                )
            )
    return findings


def _check_hardcoded_strings_in_code(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        code = _stringify(parsed_doc.doc.get("code"))
        if not code:
            continue
        for content in _iter_user_facing_code_strings(code):
            normalized = content.strip()
            if _looks_user_facing_code_string(normalized):
                findings.append(
                    _style_draft(
                        MessageId.TRANSLATABILITY_HARDCODED_USER_TEXT_IN_CODE,
                        line_number=parsed_doc.line_for_key("code"),
                        screen_id=parsed_doc.screen_id,
                        snippet=_shorten(normalized),
                    )
                )
                break
    return findings


def _check_ternary_conditional_text(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _user_facing_text_entries(docs):
        for expression in _MAKO_EXPR_RE.findall(entry.text):
            source = expression[2:-1].strip()
            try:
                parsed = ast.parse(source, mode="eval")
            except SyntaxError:
                continue
            if not any(isinstance(node, ast.IfExp) for node in ast.walk(parsed)):
                continue
            findings.append(
                _style_draft(
                    MessageId.TRANSLATABILITY_TERNARY_CONDITIONAL_TEXT,
                    line_number=entry.line_number,
                    screen_id=entry.screen_id,
                    location=entry.location,
                    snippet=_shorten(expression),
                )
            )
            break
    return findings


def _check_conditional_sentence_fragments(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _user_facing_text_entries(docs):
        fragment = _find_conditional_sentence_fragment(entry.text)
        if fragment is None:
            continue
        findings.append(
            _style_draft(
                MessageId.TRANSLATABILITY_CONDITIONAL_SENTENCE_FRAGMENT,
                line_number=entry.line_number,
                screen_id=entry.screen_id,
                location=entry.location,
                snippet=_shorten(fragment),
            )
        )
    return findings


def _find_conditional_sentence_fragment(text: str) -> str | None:
    lines = text.splitlines()
    stack: list[int] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^%\s*if\b", stripped):
            stack.append(index)
            continue
        if not re.match(r"^%\s*endif\b", stripped) or not stack:
            continue
        start = stack.pop()
        if stack:
            continue
        before = lines[start - 1].strip() if start > 0 else ""
        after = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if _is_sentence_fragment_context(before, after):
            return "\n".join(lines[start : index + 1])
    return None


def _is_sentence_fragment_context(before: str, after: str) -> bool:
    before_is_markdown_boundary = bool(
        re.match(r"^(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)", before)
    )
    if (
        before
        and not before_is_markdown_boundary
        and not re.search(r"[.!?:]\s*$", _plain_text(before))
    ):
        return True
    after_with_expressions = _MAKO_EXPR_RE.sub("value", after)
    return bool(
        after
        and not re.match(r"^(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)", after)
        and re.match(r"^[a-z0-9]", _plain_text(after_with_expressions).lstrip())
    )


def _check_subquestion_h1(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        subquestion = _stringify(parsed_doc.doc.get("subquestion"))
        match = re.search(r"(?m)^\s*#\s+.*$", subquestion)
        if not match:
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_SUBQUESTION_H1,
                line_number=parsed_doc.line_for_key("subquestion"),
                screen_id=parsed_doc.screen_id,
                snippet=_shorten(match.group(0)),
            )
        )
    return findings


def _check_language_en_flag(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        if _stringify(parsed_doc.doc.get("language")).strip().lower() != "en":
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_REMOVE_LANGUAGE_EN,
                line_number=parsed_doc.line_for_key("language"),
                screen_id=parsed_doc.screen_id,
            )
        )
    return findings


def _check_empty_screen_title(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        question_text = _plain_text(
            _visible_text(parsed_doc.doc.get("question"))
        ).strip()
        if question_text:
            continue
        has_fields = len(_iter_fields(parsed_doc.doc)) > 0
        supplemental = " ".join(
            _plain_text(_visible_text(parsed_doc.doc.get(key)))
            for key in ("subquestion", "under", "help", "note", "html")
        ).strip()
        if not has_fields and len(supplemental) < 60:
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_MISSING_SCREEN_TITLE,
                line_number=parsed_doc.default_line(),
                screen_id=parsed_doc.screen_id,
                snippet=_shorten(supplemental or "question is blank"),
            )
        )
    return findings


def _check_placeholder_language(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _iter_doc_texts(docs):
        plain = _plain_text(entry.text)
        for pattern in _PLACEHOLDER_PATTERNS:
            match = pattern.search(plain)
            if not match:
                continue
            findings.append(
                _style_draft(
                    MessageId.STYLE_PLACEHOLDER_LANGUAGE,
                    line_number=entry.line_number,
                    screen_id=entry.screen_id,
                    location=entry.location,
                    snippet=_shorten(match.group(0)),
                )
            )
            break
    return findings


def _check_plain_language_replacements(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in _iter_doc_texts(docs):
        for matched_text, replacement in _find_plain_language_suggestions(entry.text):
            key = (entry.screen_id, entry.location, matched_text.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                _style_draft(
                    MessageId.STYLE_PLAIN_LANGUAGE_REPLACEMENT,
                    line_number=entry.line_number,
                    screen_id=entry.screen_id,
                    location=entry.location,
                    matched_text=matched_text,
                    replacement=_format_plain_language_replacement(replacement),
                )
            )
    return findings


def _check_contractions(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _user_facing_text_entries(docs):
        plain = _plain_text(entry.text)
        match = _CONTRACTION_RE.search(plain)
        if not match:
            continue
        if match.group(0).lower() == "don't" and re.search(
            r"\bi\s+don't\s+know\b", plain, re.IGNORECASE
        ):
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_CONTRACTION,
                line_number=entry.line_number,
                screen_id=entry.screen_id,
                location=entry.location,
                matched_text=match.group(0),
            )
        )
    return findings


def _check_slash_alternatives(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _user_facing_text_entries(docs):
        plain = _plain_text(entry.text)
        for match in _SLASH_ALTERNATIVE_RE.finditer(plain):
            matched = match.group(0)
            if matched.lower() in _ALLOWED_SLASH_ALTERNATIVES:
                continue
            if _looks_like_url_path_fragment(plain, match.start(), match.end()):
                continue
            findings.append(
                _style_draft(
                    MessageId.STYLE_SLASH_ALTERNATIVE,
                    line_number=entry.line_number,
                    screen_id=entry.screen_id,
                    location=entry.location,
                    snippet=_shorten(matched),
                )
            )
            break
    return findings


def _check_variable_conventions(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    valid_root_re = re.compile(r"^[a-z][a-z0-9_]*$")
    bad_roots: dict[str, tuple[int, str]] = {}
    for parsed_doc in docs:
        for value, line_number in _variable_references(parsed_doc):
            root = re.split(r"[.\[]", value, maxsplit=1)[0].strip()
            if not root or valid_root_re.fullmatch(root):
                continue
            bad_roots.setdefault(root, (line_number, parsed_doc.screen_id))
    if not bad_roots:
        return []
    first_root = sorted(bad_roots.items(), key=lambda item: (item[1][0], item[0]))[0]
    return [
        _style_draft(
            MessageId.STYLE_VARIABLE_ROOT_NOT_SNAKE_CASE,
            line_number=first_root[1][0],
            screen_id=first_root[1][1],
            roots=", ".join(sorted(bad_roots)),
        )
    ]


def _check_long_sentences(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _user_facing_text_entries(docs):
        plain = _plain_text(entry.text)
        for sentence in _SENTENCE_RE.findall(plain):
            if len(_WORD_RE.findall(sentence)) <= 20:
                continue
            findings.append(
                _style_draft(
                    MessageId.STYLE_LONG_SENTENCE,
                    line_number=entry.line_number,
                    screen_id=entry.screen_id,
                    location=entry.location,
                    snippet=_shorten(sentence),
                )
            )
            break
    return findings


def _check_compound_questions(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _question_text_entries(docs):
        plain = _plain_text(entry.text).lower()
        if "?" not in plain:
            continue
        if "and/or" not in plain and not _COMPOUND_QUESTION_RE.search(plain):
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_COMPOUND_QUESTION,
                line_number=entry.line_number,
                screen_id=entry.screen_id,
                location=entry.location,
                snippet=_shorten(_plain_text(entry.text)),
            )
        )
    return findings


def _check_overlong_labels(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        question = _plain_text(_stringify(parsed_doc.doc.get("question")))
        if len(question) > 120:
            findings.append(
                _style_draft(
                    MessageId.STYLE_OVERLONG_QUESTION_LABEL,
                    line_number=parsed_doc.line_for_key("question"),
                    screen_id=parsed_doc.screen_id,
                    snippet=_shorten(question),
                )
            )
        for field in _iter_fields(parsed_doc.doc):
            field_label = _extract_field_label(field)
            if len(field_label) <= 90:
                continue
            findings.append(
                _style_draft(
                    MessageId.STYLE_OVERLONG_FIELD_LABEL,
                    line_number=parsed_doc.line_for_field(field),
                    screen_id=parsed_doc.screen_id,
                    snippet=_shorten(field_label),
                )
            )
            break
    return findings


def _check_field_label_instruction_verbs(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        for field in _iter_fields(parsed_doc.doc):
            label = _extract_field_label(field).strip()
            if not label or not _FIELD_LABEL_INSTRUCTION_VERB_RE.search(label):
                continue
            findings.append(
                _style_draft(
                    MessageId.STYLE_FIELD_LABEL_INSTRUCTION_VERB,
                    line_number=parsed_doc.line_for_field(field),
                    screen_id=parsed_doc.screen_id,
                    snippet=_shorten(label),
                )
            )
    return findings


def _check_title_case_labels(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        for field in _iter_fields(parsed_doc.doc):
            if _field_is_choice_style(field):
                continue
            label = _extract_field_label(field)
            if not _looks_like_title_case_label(label):
                continue
            findings.append(
                _style_draft(
                    MessageId.STYLE_TITLE_CASE_LABEL,
                    line_number=parsed_doc.line_for_field(field),
                    screen_id=parsed_doc.screen_id,
                    snippet=_shorten(label),
                )
            )
    return findings


def _check_other_choice_position(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        for origin, choices, line_number in _iter_choice_sources(parsed_doc):
            options = _choice_options(choices)
            if len(options) < 2:
                continue
            for index, option in enumerate(options[:-1]):
                if option["label"].strip().lower() != "other":
                    continue
                findings.append(
                    _style_draft(
                        MessageId.STYLE_OTHER_CHOICE_NOT_LAST,
                        line_number=line_number,
                        screen_id=parsed_doc.screen_id,
                        origin=origin,
                    )
                )
                break
    return findings


def _check_language_fields(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        for field in _iter_fields(parsed_doc.doc):
            if not _is_language_field(field):
                continue
            label = _extract_field_label(field) or _extract_field_variable(field)
            if _field_uses_dropdown(field):
                findings.append(
                    _style_draft(
                        MessageId.STYLE_LANGUAGE_DROPDOWN,
                        line_number=parsed_doc.line_for_field(field),
                        screen_id=parsed_doc.screen_id,
                        snippet=_shorten(label),
                    )
                )
            for option in _choice_options(field.get("choices")):
                value = option["value"].strip()
                if not value or value.lower() == "other":
                    continue
                if re.fullmatch(r"[a-z]{2,3}", value):
                    continue
                findings.append(
                    _style_draft(
                        MessageId.STYLE_LANGUAGE_CHOICE_VALUE,
                        line_number=parsed_doc.line_for_field(field),
                        screen_id=parsed_doc.screen_id,
                        snippet=_shorten(f'{option["label"]}: {value}'),
                    )
                )
                break
    return findings


def _check_pronoun_and_gender_fields(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for entry in _user_facing_text_entries(docs):
        plain = _plain_text(entry.text)
        if not re.search(r"\bpreferred\s+pronouns\b", plain, re.IGNORECASE):
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_PREFERRED_PRONOUNS,
                line_number=entry.line_number,
                screen_id=entry.screen_id,
                location=entry.location,
                snippet=_shorten(plain),
            )
        )

    for parsed_doc in docs:
        for field in _iter_fields(parsed_doc.doc):
            label = _extract_field_label(field)
            variable = _extract_field_variable(field)
            combined = f"{label} {variable}".lower()
            if re.search(r"\bpronouns?\b", combined) and _is_truthy(
                field.get("required")
            ):
                findings.append(
                    _style_draft(
                        MessageId.STYLE_REQUIRED_PRONOUN_FIELD,
                        line_number=parsed_doc.line_for_field(field),
                        screen_id=parsed_doc.screen_id,
                        snippet=_shorten(label or variable),
                    )
                )
            if not re.search(r"\bgender\b", combined):
                continue
            labels = [
                option["label"].strip().lower()
                for option in _choice_options(field.get("choices"))
                if option["label"].strip()
            ]
            if "other" in labels:
                findings.append(
                    _style_draft(
                        MessageId.STYLE_GENDER_OTHER_CHOICE,
                        line_number=parsed_doc.line_for_field(field),
                        screen_id=parsed_doc.screen_id,
                        snippet=_shorten(label or variable),
                    )
                )
            if set(labels) == {"female", "male"}:
                findings.append(
                    _style_draft(
                        MessageId.STYLE_GENDER_BINARY_ONLY,
                        line_number=parsed_doc.line_for_field(field),
                        screen_id=parsed_doc.screen_id,
                        snippet=_shorten(label or variable),
                    )
                )
    return findings


def _check_too_many_fields(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        field_count = len(_iter_fields(parsed_doc.doc))
        if field_count <= 6:
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_TOO_MANY_FIELDS_ON_SCREEN,
                line_number=parsed_doc.default_line(),
                screen_id=parsed_doc.screen_id,
                field_count=field_count,
            )
        )
    return findings


def _check_wall_of_text(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        subquestion = _stringify(parsed_doc.doc.get("subquestion"))
        plain = _plain_text(subquestion)
        word_count = len(_WORD_RE.findall(plain))
        has_structure = bool(
            re.search(r"(?m)^\s*[-*]\s+", subquestion)
            or re.search(r"(?m)^\s*#{2,6}\s+", subquestion)
        )
        if word_count <= 120 or has_structure:
            continue
        findings.append(
            _style_draft(
                MessageId.STYLE_WALL_OF_TEXT,
                line_number=parsed_doc.line_for_key("subquestion"),
                screen_id=parsed_doc.screen_id,
                snippet=_shorten(plain),
            )
        )
    return findings


def _check_question_level_help(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        help_value = parsed_doc.doc.get("help")
        if help_value is None:
            continue
        if not any(
            _stringify(parsed_doc.doc.get(key)).strip()
            for key in ("question", "subquestion", "field")
        ) and not parsed_doc.doc.get("fields"):
            continue
        help_text = _stringify(help_value).strip()
        findings.append(
            _style_draft(
                MessageId.STYLE_QUESTION_LEVEL_HELP,
                line_number=parsed_doc.line_for_key("help"),
                screen_id=parsed_doc.screen_id,
                snippet=_shorten(help_text or "help"),
            )
        )
    return findings


def _check_missing_help_on_complex_screens(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for parsed_doc in docs:
        fields = _iter_fields(parsed_doc.doc)
        if len(fields) < 5:
            continue
        has_help = bool(parsed_doc.doc.get("help"))
        for field in fields:
            if field.get("help") or field.get("hint") or field.get("note"):
                has_help = True
                break
        if has_help:
            continue
        sample_labels = [
            _extract_field_label(field) or _extract_field_variable(field)
            for field in fields
        ]
        findings.append(
            _style_draft(
                MessageId.STYLE_COMPLEX_SCREEN_MISSING_HELP,
                line_number=parsed_doc.default_line(),
                screen_id=parsed_doc.screen_id,
                snippet=_shorten(
                    ", ".join(label for label in sample_labels if label)
                    or f"{len(fields)} fields"
                ),
            )
        )
    return findings


def _check_exit_criteria_and_screen(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    metadata = _find_metadata(docs)
    screening_signal = bool(_stringify(metadata.get("can_I_use_this_form")).strip())
    for parsed_doc in docs:
        combined = " ".join(
            _stringify(parsed_doc.doc.get(key))
            for key in ("question", "subquestion", "id", "event")
        ).lower()
        if any(
            marker in combined
            for marker in (
                "can i use",
                "eligible",
                "qualify",
                "right form",
                "wrong form",
            )
        ):
            screening_signal = True
            break
    if not screening_signal:
        return []
    for parsed_doc in docs:
        combined = " ".join(
            _stringify(parsed_doc.doc.get(key))
            for key in ("question", "subquestion", "under", "id", "event")
        ).lower()
        if any(
            marker in combined
            for marker in (
                "not eligible",
                "may not be able",
                "cannot help",
                "can't help",
                "wrong form",
                "stop here",
                "exit",
            )
        ):
            return []
    line_number = docs[0].default_line() if docs else 1
    return [
        _style_draft(
            MessageId.STYLE_MISSING_EXIT_CRITERIA_SCREEN,
            line_number=line_number,
            screen_id=docs[0].screen_id if docs else None,
        )
    ]


def _check_theme_usage(docs: list[ParsedInterviewDocument]) -> list[FindingDraft]:
    metadata_docs = [
        parsed_doc
        for parsed_doc in docs
        if isinstance(parsed_doc.doc.get("metadata"), dict)
    ]
    if not metadata_docs:
        return []
    theme_references: set[str] = set()
    for parsed_doc in docs:
        include_value = parsed_doc.doc.get("include")
        theme_references.update(_iter_include_values(include_value))
        css_value = _stringify(parsed_doc.doc.get("css")).strip().lower()
        if css_value:
            theme_references.add(css_value)
        features = parsed_doc.doc.get("features")
        if isinstance(features, dict):
            bootstrap_theme = (
                _stringify(features.get("bootstrap theme")).strip().lower()
            )
            if bootstrap_theme:
                theme_references.add(bootstrap_theme)
    if any(
        marker in reference
        for reference in theme_references
        for marker in ("theme", "css", "bootstrap")
    ):
        return []
    metadata_doc = metadata_docs[0]
    return [
        _style_draft(
            MessageId.STYLE_MISSING_CUSTOM_THEME,
            line_number=metadata_doc.line_for_key("metadata"),
            screen_id=metadata_doc.screen_id,
        )
    ]


def _check_review_screen_editability(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    review_docs = [parsed_doc for parsed_doc in docs if _is_review_screen(parsed_doc)]
    if not review_docs:
        return []

    editable_variables: set[str] = set()
    for parsed_doc in review_docs:
        editable_variables.update(_review_edit_variables(parsed_doc.doc.get("review")))

    findings: list[FindingDraft] = []
    if not editable_variables:
        review_doc = review_docs[0]
        findings.append(
            _style_draft(
                MessageId.STYLE_REVIEW_SCREEN_MISSING_EDIT_LINKS,
                line_number=review_doc.default_line(),
                screen_id=review_doc.screen_id,
            )
        )
        return findings

    key_choice_variables = sorted(
        {
            field_var
            for parsed_doc in docs
            for field in _iter_fields(parsed_doc.doc)
            if _field_looks_like_key_choice(field)
            for field_var in [_extract_field_variable(field).strip()]
            if field_var
        }
    )
    if key_choice_variables and not any(
        _variable_name_matches(edit_name, key_choice)
        for edit_name in editable_variables
        for key_choice in key_choice_variables
    ):
        review_doc = review_docs[0]
        findings.append(
            _style_draft(
                MessageId.STYLE_REVIEW_SCREEN_MISSING_KEY_CHOICE_EDITS,
                line_number=review_doc.default_line(),
                screen_id=review_doc.screen_id,
                snippet=", ".join(key_choice_variables[:4]),
            )
        )
    return findings


def _check_prefer_person_objects(
    docs: list[ParsedInterviewDocument],
) -> list[FindingDraft]:
    references = [
        (reference, line_number, parsed_doc.screen_id)
        for parsed_doc in docs
        for reference, line_number in _variable_references(parsed_doc)
    ]
    if not references:
        return []
    if any(
        marker in reference
        for reference, _, _ in references
        for marker in (".name.", ".address.", ".birthdate", ".gender")
    ):
        return []
    name_parts = [
        item
        for item in references
        if re.search(r"(first|middle|last|full)_name$", item[0])
    ]
    address_parts = [
        item
        for item in references
        if re.search(r"(address|street|unit|city|state|zip|postal_code)$", item[0])
    ]
    if len(name_parts) < 2 and len(address_parts) < 3:
        return []
    first_reference, line_number, screen_id = sorted(
        name_parts + address_parts,
        key=lambda item: (item[1], item[0]),
    )[0]
    return [
        _style_draft(
            MessageId.STYLE_PREFER_PERSON_OBJECTS,
            line_number=line_number,
            screen_id=screen_id,
            snippet=first_reference,
        )
    ]


def _run_llm_rules(
    *,
    parsed_docs: list[ParsedInterviewDocument],
    input_file: str | None,
    options: StyleLintOptions,
) -> list[Finding]:
    prompts = _load_llm_prompt_templates()
    llm_rules = prompts.get("llm_rules")
    if not isinstance(llm_rules, list):
        return []
    screen_payload = _build_screen_payload(parsed_docs)
    if not screen_payload:
        return []
    findings: list[Finding] = []
    for rule in llm_rules:
        if not isinstance(rule, dict):
            continue
        rule_id = _stringify(rule.get("rule_id")).strip()
        system_prompt = _stringify(rule.get("system_prompt"))
        user_prompt = _stringify(rule.get("user_prompt")).replace(
            "{screens_json}", screen_payload
        )
        raw_response, error_detail = _call_openai_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            base_url=options.resolved_openai_base_url(),
            api_key=options.resolved_openai_api_key(),
            model=options.resolved_openai_model(),
        )
        if error_detail is not None:
            findings.append(
                make_finding(
                    MessageId.STYLE_LLM_REQUEST_FAILED,
                    file_name=input_file,
                    line_number=parsed_docs[0].default_line() if parsed_docs else 1,
                    screen_id=parsed_docs[0].screen_id if parsed_docs else "",
                    rule_id=rule_id or "style-llm",
                    detail=error_detail,
                )
            )
            continue
        for item in _safe_parse_llm_json(raw_response):
            finding = _build_llm_finding(
                parsed_docs=parsed_docs,
                input_file=input_file,
                rule_id=_stringify(item.get("rule_id")).strip() or rule_id,
                message=_stringify(item.get("message")).strip()
                or "LLM identified a potential style issue.",
                problematic_text=_stringify(item.get("problematic_text")).strip(),
                screen_id=_stringify(item.get("screen_id")).strip(),
            )
            if finding is not None:
                findings.append(finding)
    return findings


def _build_llm_finding(
    *,
    parsed_docs: list[ParsedInterviewDocument],
    input_file: str | None,
    rule_id: str,
    message: str,
    problematic_text: str,
    screen_id: str,
) -> Finding | None:
    message_id: str
    if rule_id == "tone-and-respect":
        message_id = MessageId.STYLE_TONE_AND_RESPECT
    elif rule_id == "plain-language-rewrite-opportunities":
        message_id = MessageId.STYLE_PLAIN_LANGUAGE_REWRITE_OPPORTUNITY
    else:
        return None
    line_number = next(
        (
            parsed_doc.default_line()
            for parsed_doc in parsed_docs
            if parsed_doc.screen_id == screen_id
        ),
        parsed_docs[0].default_line() if parsed_docs else 1,
    )
    rendered_message = message
    if problematic_text:
        rendered_message = f'{message} Quote: "{_shorten(problematic_text, limit=220)}"'
    return make_finding(
        message_id,
        file_name=input_file,
        line_number=line_number,
        message=rendered_message,
        screen_id=screen_id,
        snippet=_shorten(problematic_text, limit=220) if problematic_text else "",
    )


def _iter_doc_texts(docs: list[ParsedInterviewDocument]) -> list[TextEntry]:
    values: list[TextEntry] = []
    for parsed_doc in docs:
        for key in VISIBLE_TEXT_KEYS:
            value = parsed_doc.doc.get(key)
            line_number = parsed_doc.line_for_key(key)
            if isinstance(value, dict):
                content = _stringify(value.get("content"))
                label = _stringify(value.get("label"))
                if content:
                    values.append(
                        TextEntry(
                            location=f"{key}.content",
                            text=content,
                            line_number=line_number,
                            screen_id=parsed_doc.screen_id,
                        )
                    )
                if label:
                    values.append(
                        TextEntry(
                            location=f"{key}.label",
                            text=label,
                            line_number=line_number,
                            screen_id=parsed_doc.screen_id,
                        )
                    )
            else:
                rendered = _stringify(value)
                if rendered:
                    values.append(
                        TextEntry(
                            location=key,
                            text=rendered,
                            line_number=line_number,
                            screen_id=parsed_doc.screen_id,
                        )
                    )
        for index, field in enumerate(_iter_fields(parsed_doc.doc)):
            line_number = parsed_doc.line_for_field(field)
            for field_key in ("label", "help", "hint", "note", "html"):
                rendered = _stringify(field.get(field_key))
                if not rendered:
                    continue
                values.append(
                    TextEntry(
                        location=f"fields[{index}].{field_key}",
                        text=rendered,
                        line_number=line_number,
                        screen_id=parsed_doc.screen_id,
                    )
                )
            if not field.get("label") and field:
                first_key = _stringify(next(iter(field.keys())))
                if first_key:
                    values.append(
                        TextEntry(
                            location=f"fields[{index}].first_key",
                            text=first_key,
                            line_number=line_number,
                            screen_id=parsed_doc.screen_id,
                        )
                    )
    return values


def _user_facing_text_entries(docs: list[ParsedInterviewDocument]) -> list[TextEntry]:
    entries = _iter_doc_texts(docs)
    for parsed_doc in docs:
        for key in ("choices", "dropdown", "buttons"):
            for label in _extract_choice_display_text(parsed_doc.doc.get(key)):
                entries.append(
                    TextEntry(
                        location=key,
                        text=label,
                        line_number=parsed_doc.line_for_key(key),
                        screen_id=parsed_doc.screen_id,
                    )
                )
        for index, field in enumerate(_iter_fields(parsed_doc.doc)):
            for label in _extract_choice_display_text(field.get("choices")):
                entries.append(
                    TextEntry(
                        location=f"fields[{index}].choices",
                        text=label,
                        line_number=parsed_doc.line_for_field(field),
                        screen_id=parsed_doc.screen_id,
                    )
                )
    return entries


def _question_text_entries(docs: list[ParsedInterviewDocument]) -> list[TextEntry]:
    entries: list[TextEntry] = []
    for parsed_doc in docs:
        for key in ("question", "subquestion"):
            value = _stringify(parsed_doc.doc.get(key))
            if not value:
                continue
            entries.append(
                TextEntry(
                    location=key,
                    text=value,
                    line_number=parsed_doc.line_for_key(key),
                    screen_id=parsed_doc.screen_id,
                )
            )
    return entries


def _extract_choice_display_text(choices: Any) -> list[str]:
    extracted: list[str] = []
    if isinstance(choices, list):
        for choice in choices:
            if isinstance(choice, str):
                extracted.append(choice.split(": ", 1)[0] if ": " in choice else choice)
            elif isinstance(choice, dict):
                label = _stringify(choice.get("label"))
                if label:
                    extracted.append(label)
                else:
                    display_items = [
                        key for key in choice.keys() if _stringify(key) != "__line__"
                    ]
                    if len(display_items) == 1:
                        extracted.append(_stringify(display_items[0]))
    elif isinstance(choices, dict):
        extracted.extend(_stringify(key) for key in choices.keys())
    return [item for item in extracted if item]


def _iter_choice_sources(
    parsed_doc: ParsedInterviewDocument,
) -> list[tuple[str, Any, int]]:
    sources: list[tuple[str, Any, int]] = []
    for key in ("choices", "dropdown", "buttons"):
        if parsed_doc.doc.get(key) is not None:
            sources.append((key, parsed_doc.doc.get(key), parsed_doc.line_for_key(key)))
    for index, field in enumerate(_iter_fields(parsed_doc.doc)):
        if field.get("choices") is not None:
            sources.append(
                (
                    f"fields[{index}].choices",
                    field.get("choices"),
                    parsed_doc.line_for_field(field),
                )
            )
    return sources


def _choice_options(choices: Any) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    if isinstance(choices, list):
        for choice in choices:
            if isinstance(choice, str):
                label, value = _split_choice_string(choice)
                options.append({"label": label, "value": value})
            elif isinstance(choice, dict):
                label = _stringify(choice.get("label")).strip()
                value = _stringify(choice.get("value")).strip()
                if label or value:
                    options.append({"label": label, "value": value})
                else:
                    display_items = [
                        (key, val)
                        for key, val in choice.items()
                        if _stringify(key) != "__line__"
                    ]
                    if len(display_items) != 1:
                        continue
                    key, val = display_items[0]
                    options.append(
                        {
                            "label": _stringify(key).strip(),
                            "value": _stringify(val).strip(),
                        }
                    )
    elif isinstance(choices, dict):
        for key, value in choices.items():
            options.append(
                {"label": _stringify(key).strip(), "value": _stringify(value).strip()}
            )
    return [option for option in options if option["label"] or option["value"]]


def _split_choice_string(choice: str) -> tuple[str, str]:
    if ": " not in choice:
        return choice.strip(), ""
    label, value = choice.split(": ", 1)
    return label.strip(), value.strip()


def _looks_like_title_case_label(value: str) -> bool:
    if not value or "?" in value or "${" in value:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", value)
    candidates = [
        word
        for word in words
        if len(word) > 2
        and not word.isupper()
        and word.lower() not in {"and", "for", "the", "with", "from"}
    ]
    if len(candidates) < 3:
        return False
    title_words = [
        word
        for word in candidates
        if word[:1].isupper() and word[1:] == word[1:].lower()
    ]
    return len(title_words) / len(candidates) >= 0.75


def _is_language_field(field: dict[str, Any]) -> bool:
    combined = " ".join((_extract_field_label(field), _extract_field_variable(field)))
    return bool(re.search(r"\blanguage\b", combined, re.IGNORECASE))


def _field_uses_dropdown(field: dict[str, Any]) -> bool:
    return (
        any(
            _stringify(field.get(key)).strip().lower() == "dropdown"
            for key in ("datatype", "input type")
        )
        or field.get("dropdown") is not None
    )


def _field_is_choice_style(field: dict[str, Any]) -> bool:
    datatype = _stringify(field.get("datatype")).strip().lower()
    return datatype in {
        "checkboxes",
        "checkbox",
        "yesno",
        "noyes",
        "yesnomaybe",
        "noyesmaybe",
        "radio",
    }


def _looks_like_url_path_fragment(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 20) : start]
    suffix = text[end : min(len(text), end + 20)]
    if re.search(r"(?:https?://|www\.)\S*$", prefix, re.IGNORECASE):
        return True
    if prefix.endswith(".") or "/" in prefix[-2:]:
        return True
    return bool(re.match(r"\.[A-Za-z0-9]", suffix))


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def _variable_references(
    parsed_doc: ParsedInterviewDocument,
) -> list[tuple[str, int]]:
    references: list[tuple[str, int]] = []
    for key in ("yesno", "noyes", "yesnomaybe", "noyesmaybe"):
        value = _stringify(parsed_doc.doc.get(key)).strip()
        if value and _looks_like_variable_reference(value):
            references.append((value, parsed_doc.line_for_key(key)))
    for field in _iter_fields(parsed_doc.doc):
        value = _extract_field_variable(field)
        if value and _looks_like_variable_reference(value):
            references.append((value, parsed_doc.line_for_field(field)))
    return references


def _looks_like_variable_reference(value: str) -> bool:
    stripped = value.strip()
    return bool(
        re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\]|\.[A-Za-z_][A-Za-z0-9_]*)*",
            stripped,
        )
    )


def _looks_user_facing_code_string(value: str) -> bool:
    if (
        " " not in value
        or value.startswith("http")
        or re.fullmatch(r"[A-Za-z0-9_./:-]+", value)
    ):
        return False
    letters_only = re.sub(r"[^A-Za-z ]+", " ", value).strip()
    if not letters_only:
        return False
    if letters_only == letters_only.lower() and not re.search(r"[.!?:]", value):
        return False
    return True


def _iter_user_facing_code_strings(code: str) -> list[str]:
    contents: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return contents
    parents = _parent_map(tree)
    docstrings = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Constant)
            or not isinstance(node.value, str)
            or node in docstrings
        ):
            continue
        content = node.value.strip()
        if not content or not _has_user_facing_code_sink(node, parents):
            continue
        contents.append(content)
    return contents


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _docstring_nodes(tree: ast.AST) -> set[ast.Constant]:
    docstrings: set[ast.Constant] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first_stmt = body[0]
        if not isinstance(first_stmt, ast.Expr):
            continue
        value = getattr(first_stmt, "value", None)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            docstrings.add(value)
    return docstrings


def _has_user_facing_code_sink(
    node: ast.Constant, parents: dict[ast.AST, ast.AST]
) -> bool:
    current: ast.AST = node
    while current in parents:
        parent = parents[current]
        if isinstance(parent, ast.keyword) and _is_user_facing_code_name(
            parent.arg or ""
        ):
            return True
        if isinstance(parent, ast.Call) and _is_user_facing_code_call(parent):
            return True
        if isinstance(parent, ast.Assign) and any(
            _is_user_facing_assignment_target(target) for target in parent.targets
        ):
            return True
        if isinstance(parent, ast.AnnAssign) and _is_user_facing_assignment_target(
            parent.target
        ):
            return True
        if isinstance(parent, ast.NamedExpr) and _is_user_facing_assignment_target(
            parent.target
        ):
            return True
        if isinstance(parent, ast.Dict) and _dict_value_has_user_facing_key(
            parent, current
        ):
            return True
        current = parent
    return False


def _is_user_facing_code_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in _USER_FACING_CODE_CALLS
    if isinstance(func, ast.Attribute):
        return func.attr in _USER_FACING_CODE_CALLS
    return False


def _is_user_facing_assignment_target(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return _is_user_facing_code_name(target.id)
    if isinstance(target, ast.Attribute):
        return _is_user_facing_code_name(target.attr)
    return False


def _dict_value_has_user_facing_key(mapping: ast.Dict, node: ast.AST) -> bool:
    for key, value in zip(mapping.keys, mapping.values):
        if value is not node:
            continue
        return _is_user_facing_code_name(_dict_key_string(key))
    return False


def _dict_key_string(node: ast.expr | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _is_user_facing_code_name(name: str) -> bool:
    lowered = _stringify(name).strip().lower()
    if not lowered:
        return False
    if lowered in _USER_FACING_CODE_EXACT_NAMES:
        return True
    parts = [part for part in re.split(r"[^a-z0-9]+", lowered) if part]
    return any(part in _USER_FACING_CODE_NAME_PARTS for part in parts)


def _find_metadata(docs: list[ParsedInterviewDocument]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for parsed_doc in docs:
        block = parsed_doc.doc.get("metadata")
        if isinstance(block, dict):
            metadata.update(block)
    return metadata


def _iter_include_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_stringify(value).strip().lower()]
    if isinstance(value, list):
        return [
            _stringify(item).strip().lower()
            for item in value
            if _stringify(item).strip()
        ]
    return []


def _is_review_screen(parsed_doc: ParsedInterviewDocument) -> bool:
    if parsed_doc.doc.get("review") is not None:
        return True
    combined = " ".join(
        _stringify(parsed_doc.doc.get(key)) for key in ("question", "id", "event")
    ).lower()
    return bool(
        re.search(
            r"\b(?:review|check your answers|edit your answers)\b",
            combined,
        )
    )


def _review_edit_variables(review_value: Any) -> set[str]:
    variables: set[str] = set()
    if isinstance(review_value, list):
        for item in review_value:
            if isinstance(item, dict):
                edit_value = _stringify(item.get("Edit")).strip()
                if edit_value:
                    variables.add(edit_value)
    elif isinstance(review_value, dict):
        edit_value = _stringify(review_value.get("Edit")).strip()
        if edit_value:
            variables.add(edit_value)
    return variables


def _field_looks_like_key_choice(field: dict[str, Any]) -> bool:
    datatype = _stringify(field.get("datatype")).strip().lower()
    if datatype in {"yesno", "noyes", "yesnomaybe", "noyesmaybe", "radio"}:
        return True
    choices = field.get("choices")
    return isinstance(choices, (list, dict))


def _variable_name_matches(left: str, right: str) -> bool:
    left_text = _stringify(left).strip()
    right_text = _stringify(right).strip()
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    return left_text.split(".")[0] == right_text.split(".")[0]


def _plain_text(text: str) -> str:
    rendered = _strip_mako(text)
    rendered = _FILE_TAG_RE.sub(" ", rendered)
    rendered = _MARKDOWN_IMAGE_RE.sub(r" \1 ", rendered)
    rendered = _MARKDOWN_LINK_RE.sub(r" \1 ", rendered)
    rendered = _MARKDOWN_CODE_RE.sub(r" \1 ", rendered)
    rendered = _HTML_TAG_RE.sub(" ", rendered)
    rendered = html.unescape(rendered)
    rendered = re.sub(r"(?m)^\s*#{1,6}\s+", "", rendered)
    rendered = re.sub(r"(?m)^\s*[-*+]\s+", "", rendered)
    return re.sub(r"\s+", " ", rendered).strip()


def _strip_mako(text: str) -> str:
    rendered = _MAKO_BLOCK_RE.sub(" ", text)
    rendered = _MAKO_EXPR_RE.sub(" ", rendered)
    rendered = _MAKO_CONTROL_RE.sub(" ", rendered)
    return rendered


def _stringify(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, str):
        return item
    return str(item)


def _visible_text(item: Any) -> str:
    if isinstance(item, dict):
        return " ".join(
            part
            for part in (_stringify(item.get("label")), _stringify(item.get("content")))
            if part
        )
    return _stringify(item)


def _shorten(text: Any, limit: int = 180) -> str:
    value = re.sub(r"\s+", " ", _stringify(text)).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


@lru_cache(maxsize=None)
def _load_yaml_data_file(filename: str) -> Any:
    yaml = YAML(typ="safe")
    data_path = importlib.resources.files("dayamlchecker").joinpath("data", filename)
    return yaml.load(data_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _load_llm_prompt_templates() -> dict[str, Any]:
    loaded = _load_yaml_data_file("interview_linter_prompts.yml")
    return loaded if isinstance(loaded, dict) else {}


@lru_cache(maxsize=None)
def _load_plain_language_replacements() -> dict[str, str]:
    loaded = _load_yaml_data_file("plain_language_replacements.yml")
    if not isinstance(loaded, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in loaded.items():
        term = _stringify(key).strip().lower().replace("’", "'")
        replacement = _stringify(value).strip()
        if term and replacement:
            normalized[term] = replacement
    return normalized


@lru_cache(maxsize=None)
def _compiled_plain_language_patterns() -> list[tuple[str, str, re.Pattern[str]]]:
    compiled: list[tuple[str, str, re.Pattern[str]]] = []
    sorted_terms = sorted(
        _load_plain_language_replacements().items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for term, replacement in sorted_terms:
        if not re.search(r"[a-z0-9]", term):
            continue
        compiled.append(
            (
                term,
                replacement,
                re.compile(
                    rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
                    re.IGNORECASE,
                ),
            )
        )
    return compiled


def _find_plain_language_suggestions(
    text: str, max_matches: int = 8
) -> list[tuple[str, str]]:
    plain = _plain_text(text)
    if not plain:
        return []
    occupied: list[tuple[int, int]] = []
    seen_terms: set[str] = set()
    matches: list[tuple[int, str, str]] = []
    for _, replacement, pattern in _compiled_plain_language_patterns():
        if len(matches) >= max_matches:
            break
        for found in pattern.finditer(plain):
            span = (found.start(), found.end())
            overlaps = any(
                not (span[1] <= used_start or span[0] >= used_end)
                for used_start, used_end in occupied
            )
            if overlaps:
                continue
            seen_key = found.group(0).strip().lower()
            if seen_key in seen_terms:
                continue
            seen_terms.add(seen_key)
            occupied.append(span)
            matches.append((found.start(), found.group(0), replacement))
            break
    matches.sort(key=lambda item: item[0])
    return [(match_text, replacement) for _, match_text, replacement in matches]


def _format_plain_language_replacement(value: str) -> str:
    formatted = _stringify(value).strip()
    if formatted.startswith("[") and formatted.endswith("]"):
        formatted = formatted[1:-1].strip()
    return formatted


def _build_screen_payload(parsed_docs: list[ParsedInterviewDocument]) -> str:
    payload = []
    for parsed_doc in parsed_docs[:40]:
        screen_text = "\n\n".join(
            _visible_text(parsed_doc.doc.get(key))
            for key in ("question", "subquestion", "under", "help", "note", "html")
            if _visible_text(parsed_doc.doc.get(key)).strip()
        )
        screen_text = _shorten(_plain_text(screen_text), limit=800)
        if not screen_text:
            continue
        payload.append({"screen_id": parsed_doc.screen_id, "text": screen_text})
    return json.dumps(payload, ensure_ascii=False)


def _call_openai_chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    api_key: str,
    model: str,
) -> tuple[Any | None, str | None]:
    request_url = base_url.rstrip("/")
    if not request_url.endswith("/chat/completions"):
        request_url = f"{request_url}/chat/completions"
    try:
        response = requests.post(
            request_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
    except requests.RequestException:
        return None, "network request failed"
    if response.status_code >= 400:
        return None, f"provider returned HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return None, "provider returned a non-JSON response"
    try:
        return payload["choices"][0]["message"]["content"], None
    except (KeyError, IndexError, TypeError):
        return None, "provider response was missing completion text"


def _safe_parse_llm_json(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        if isinstance(raw.get("findings"), list):
            return [item for item in raw["findings"] if isinstance(item, dict)]
        return [raw]
    if isinstance(raw, str):
        try:
            return _safe_parse_llm_json(json.loads(raw))
        except ValueError:
            return []
    return []


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    unique: list[Finding] = []
    seen: set[tuple[str, str, int]] = set()
    for finding in findings:
        key = (finding.code, finding.message, finding.line_number or 0)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique
