from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FindingClass(StrEnum):
    GENERAL = "general"
    ACCESSIBILITY = "accessibility"


class MessageId(StrEnum):
    YAML_DUPLICATE_KEY = "yaml_duplicate_key"
    YAML_PARSE_ERROR = "yaml_parse_error"
    YAML_STRING_REQUIRED = "yaml_string_required"

    MAKO_SYNTAX_ERROR = "mako_syntax_error"
    MAKO_COMPILE_ERROR = "mako_compile_error"
    FIELD_VALUE_MAKO_SYNTAX_ERROR = "field_value_mako_syntax_error"
    FIELD_VALUE_MAKO_COMPILE_ERROR = "field_value_mako_compile_error"

    PYTHON_CODE_TYPE = "python_code_type"
    PYTHON_SYNTAX_ERROR = "python_syntax_error"
    VALIDATION_CODE_MISSING_VALIDATION_ERROR = (
        "validation_code_missing_validation_error"
    )
    PYTHON_BOOL_NUMBER = "python_bool_number"
    PYTHON_BOOL_TYPE = "python_bool_type"
    PYTHON_BOOL_SYNTAX = "python_bool_syntax"

    JS_MODIFIER_TYPE = "js_modifier_type"
    JS_INVALID_SYNTAX = "js_invalid_syntax"
    JS_MISSING_VAL_CALL = "js_missing_val_call"
    JS_UNKNOWN_SCREEN_FIELD = "js_unknown_screen_field"
    JS_UNKNOWN_SCREEN_FIELD_PARTIAL = "js_unknown_screen_field_partial"
    JS_VAL_ARG_NOT_QUOTED = "js_val_arg_not_quoted"

    UNKNOWN_KEYS = "unknown_keys"
    SHOW_IF_MALFORMED = "show_if_malformed"
    SHOW_IF_CODE_TYPE = "show_if_code_type"
    SHOW_IF_CODE_SYNTAX = "show_if_code_syntax"
    SHOW_IF_DICT_KEYS = "show_if_dict_keys"
    NO_POSSIBLE_TYPES = "no_possible_types"
    TOO_MANY_TYPES = "too_many_types"
    INTERVIEW_ORDER_UNMATCHED_GUARD = "interview_order_unmatched_guard"
    NESTED_VISIBILITY_LOGIC = "nested_visibility_logic"

    PYTHON_VAR_TYPE = "python_var_type"
    PYTHON_VAR_WHITESPACE = "python_var_whitespace"
    OBJECTS_BLOCK_TYPE = "objects_block_type"
    FIELDS_CODE_TYPE = "fields_code_type"
    FIELDS_DICT_KEYS = "fields_dict_keys"
    FIELDS_TYPE = "fields_type"
    FIELD_MODIFIER_VARIABLE_TYPE = "field_modifier_variable_type"
    FIELD_MODIFIER_UNKNOWN_VARIABLE_DICT = "field_modifier_unknown_variable_dict"
    FIELD_MODIFIER_CODE_ERROR = "field_modifier_code_error"
    FIELD_MODIFIER_SAME_SCREEN_CODE = "field_modifier_same_screen_code"
    FIELD_MODIFIER_DICT_KEYS = "field_modifier_dict_keys"
    FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING = (
        "field_modifier_unknown_variable_string"
    )
    FIELD_MODIFIER_CASE = "field_modifier_case"

    ACCESSIBILITY_COMBOBOX_NOT_ACCESSIBLE = "accessibility_combobox_not_accessible"
    ACCESSIBILITY_NO_LABEL_MULTI_FIELD = "accessibility_no_label_multi_field"
    ACCESSIBILITY_TAGGED_PDF_NOT_ENABLED = (
        "accessibility_tagged_pdf_not_enabled"
    )
    ACCESSIBILITY_THEME_CONTRAST_TOO_LOW = (
        "accessibility_theme_contrast_too_low"
    )
    ACCESSIBILITY_IMAGE_MISSING_ALT_TEXT = (
        "accessibility_image_missing_alt_text"
    )
    ACCESSIBILITY_MARKDOWN_HEADING_LEVEL_SKIP = (
        "accessibility_markdown_heading_level_skip"
    )
    ACCESSIBILITY_HTML_HEADING_LEVEL_SKIP = (
        "accessibility_html_heading_level_skip"
    )
    ACCESSIBILITY_EMPTY_LINK_TEXT = "accessibility_empty_link_text"
    ACCESSIBILITY_NON_DESCRIPTIVE_LINK_TEXT = (
        "accessibility_non_descriptive_link_text"
    )

    URL_CONCATENATED_ERROR = "url_concatenated_error"
    URL_CONCATENATED_WARNING = "url_concatenated_warning"
    URL_BROKEN_ERROR = "url_broken_error"
    URL_BROKEN_WARNING = "url_broken_warning"
    URL_UNREACHABLE_ERROR = "url_unreachable_error"
    URL_UNREACHABLE_WARNING = "url_unreachable_warning"


@dataclass(frozen=True, slots=True)
class MessageDefinition:
    code: str
    severity: Severity
    finding_class: FindingClass
    summary: str
    template: str


MESSAGE_DEFINITIONS: dict[str, MessageDefinition] = {
    MessageId.YAML_DUPLICATE_KEY: MessageDefinition(
        code="EG101",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Duplicate YAML key",
        template="{error}",
    ),
    MessageId.YAML_PARSE_ERROR: MessageDefinition(
        code="EG102",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="YAML parsing error",
        template="{error}",
    ),
    MessageId.YAML_STRING_REQUIRED: MessageDefinition(
        code="EG103",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Expected a YAML string",
        template="expected a YAML string, got {value_repr}",
    ),
    MessageId.MAKO_SYNTAX_ERROR: MessageDefinition(
        code="EG111",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Invalid Mako syntax",
        template="{error}",
    ),
    MessageId.MAKO_COMPILE_ERROR: MessageDefinition(
        code="EG112",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Mako compile error",
        template="{error}",
    ),
    MessageId.FIELD_VALUE_MAKO_SYNTAX_ERROR: MessageDefinition(
        code="EG111",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Invalid Mako syntax",
        template="{field_key} value has {error}",
    ),
    MessageId.FIELD_VALUE_MAKO_COMPILE_ERROR: MessageDefinition(
        code="EG112",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Mako compile error",
        template="{field_key} value has {error}",
    ),
    MessageId.PYTHON_CODE_TYPE: MessageDefinition(
        code="EG121",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Python code block must be a YAML string",
        template="code block must be a YAML string, got {value_type}",
    ),
    MessageId.PYTHON_SYNTAX_ERROR: MessageDefinition(
        code="EG122",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Python syntax error",
        template="Python syntax error: {error}",
    ),
    MessageId.VALIDATION_CODE_MISSING_VALIDATION_ERROR: MessageDefinition(
        code="WG101",
        severity=Severity.WARNING,
        finding_class=FindingClass.GENERAL,
        summary="Validation code may not show user-facing feedback",
        template=(
            "validation code does not call validation_error(); consider calling "
            "validation_error(...) to provide user-facing error messages"
        ),
    ),
    MessageId.PYTHON_BOOL_NUMBER: MessageDefinition(
        code="EG131",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Expected a Python boolean or expression",
        template="expected True, False, or a Python expression, got number: {value}",
    ),
    MessageId.PYTHON_BOOL_TYPE: MessageDefinition(
        code="EG132",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Expected a Python boolean or expression",
        template="expected True, False, or a Python expression, got: {value_type}",
    ),
    MessageId.PYTHON_BOOL_SYNTAX: MessageDefinition(
        code="EG133",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Invalid Python boolean expression",
        template=(
            "expected True, False, or a valid Python expression, got: {value!r} "
            "(Python syntax error: {error})"
        ),
    ),
    MessageId.JS_MODIFIER_TYPE: MessageDefinition(
        code="EG203",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="JavaScript modifier must be a string",
        template="{modifier_key} must be a string, got {value_type}",
    ),
    MessageId.JS_INVALID_SYNTAX: MessageDefinition(
        code="EG204",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Invalid JavaScript syntax",
        template="invalid JavaScript syntax in {modifier_key}: {error}",
    ),
    MessageId.JS_MISSING_VAL_CALL: MessageDefinition(
        code="EG205",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="JavaScript modifier must reference an on-screen field",
        template=(
            "{modifier_key} must contain at least one val() call to reference "
            "an on-screen field"
        ),
    ),
    MessageId.JS_UNKNOWN_SCREEN_FIELD: MessageDefinition(
        code="EG206",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="JavaScript modifier references a missing on-screen field",
        template=(
            '{modifier_key} references val("{var_name}"), but "{var_name}" is '
            "not defined on this screen"
        ),
    ),
    MessageId.JS_UNKNOWN_SCREEN_FIELD_PARTIAL: MessageDefinition(
        code="WG206",
        severity=Severity.WARNING,
        finding_class=FindingClass.GENERAL,
        summary="JavaScript modifier could not be fully validated",
        template=(
            '{modifier_key} references val("{var_name}"), but "{var_name}" is not '
            "defined on this screen (unable to fully validate screen variables "
            "because this screen uses fields: code)"
        ),
    ),
    MessageId.JS_VAL_ARG_NOT_QUOTED: MessageDefinition(
        code="EG207",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="val() argument must be a quoted string literal",
        template=(
            'val() argument must be a quoted string literal, not "{bad_arg}". '
            'Use val("...") or val(\'...\') instead'
        ),
    ),
    MessageId.UNKNOWN_KEYS: MessageDefinition(
        code="EG301",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Unknown YAML keys",
        template="keys that should not appear in a docassemble block: {keys}",
    ),
    MessageId.SHOW_IF_MALFORMED: MessageDefinition(
        code="EG302",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Malformed show if shorthand",
        template=(
            'show if value "{value}" appears malformed. Use YAML dict syntax: '
            "show if: {{ variable: var_name, is: value }} or show if: {{ code: ... }}"
        ),
    ),
    MessageId.SHOW_IF_CODE_TYPE: MessageDefinition(
        code="EG303",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="show if: code must be a YAML string",
        template="show if: code must be a YAML string",
    ),
    MessageId.SHOW_IF_CODE_SYNTAX: MessageDefinition(
        code="EG304",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="show if: code has a Python syntax error",
        template="show if: code has a Python syntax error: {error}",
    ),
    MessageId.SHOW_IF_DICT_KEYS: MessageDefinition(
        code="EG305",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary='show if dict must include "variable" or "code"',
        template='show if dict must include either "variable" or "code"',
    ),
    MessageId.NO_POSSIBLE_TYPES: MessageDefinition(
        code="EG306",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="No recognized block type found",
        template=(
            "couldn't identify a block type: no valid combination of keys found "
            "(looking for keys like question, include, metadata, code, objects, etc. "
            "See https://docassemble.org/docs.html)"
        ),
    ),
    MessageId.TOO_MANY_TYPES: MessageDefinition(
        code="EG307",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Block matches too many exclusive interview types",
        template="block matches too many exclusive interview types: {block_types}",
    ),
    MessageId.INTERVIEW_ORDER_UNMATCHED_GUARD: MessageDefinition(
        code="EG308",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Interview-order block is missing a matching show/hide guard",
        template=(
            'interview-order style block references "{field_name}" without a matching '
            "guard for that field's show/hide logic; this can cause the interview "
            "to get stuck"
        ),
    ),
    MessageId.NESTED_VISIBILITY_LOGIC: MessageDefinition(
        code="WG309",
        severity=Severity.WARNING,
        finding_class=FindingClass.GENERAL,
        summary="Show/hide visibility logic is nested too deeply",
        template=(
            "show if/hide if visibility logic is nested {nesting_depth} levels on "
            "this screen (more than 2)"
        ),
    ),
    MessageId.PYTHON_VAR_TYPE: MessageDefinition(
        code="EG401",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Python variable reference must be a YAML string",
        template="the Python variable reference must be a YAML string, got {value_repr}",
    ),
    MessageId.PYTHON_VAR_WHITESPACE: MessageDefinition(
        code="EG402",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Python variable reference cannot contain whitespace",
        template="the Python variable reference cannot contain whitespace, got {value}",
    ),
    MessageId.OBJECTS_BLOCK_TYPE: MessageDefinition(
        code="EG403",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="objects block must be a list or dict",
        template="objects block must be a list or dict, got {value_repr}",
    ),
    MessageId.FIELDS_CODE_TYPE: MessageDefinition(
        code="EG404",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="fields: code must be a YAML string",
        template="fields: code must be a YAML string, got {value_type}",
    ),
    MessageId.FIELDS_DICT_KEYS: MessageDefinition(
        code="EG405",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary='fields dict must contain a "code" key',
        template=(
            'fields dict must contain a "code" key when written as a mapping, '
            "got {value_repr}"
        ),
    ),
    MessageId.FIELDS_TYPE: MessageDefinition(
        code="EG406",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="fields must be a list or dict",
        template="fields must be a list or dict, got {value_repr}",
    ),
    MessageId.FIELD_MODIFIER_VARIABLE_TYPE: MessageDefinition(
        code="EG407",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Field modifier variable must be a string",
        template="{modifier_key}: variable must be a string, got {value_type}",
    ),
    MessageId.FIELD_MODIFIER_UNKNOWN_VARIABLE_DICT: MessageDefinition(
        code="EG408",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Field modifier references a field not defined on this screen",
        template=(
            '{modifier_key}: variable "{variable}" is not defined on this screen. '
            "Use {modifier_key}: {{ code: ... }} instead for variables from previous screens"
        ),
    ),
    MessageId.FIELD_MODIFIER_CODE_ERROR: MessageDefinition(
        code="EG409",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Field modifier code contains another validation error",
        template="{modifier_key}: code has {detail}",
    ),
    MessageId.FIELD_MODIFIER_SAME_SCREEN_CODE: MessageDefinition(
        code="EG410",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="show if: code references a variable defined on this screen",
        template=(
            "{modifier_key}: code references variable(s) defined on this screen "
            "({variables}). Use {modifier_key}: <var> or {modifier_key}: "
            "{{ variable: <var>, is: ... }} instead"
        ),
    ),
    MessageId.FIELD_MODIFIER_DICT_KEYS: MessageDefinition(
        code="EG411",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary='Field modifier dict must include "variable" or "code"',
        template='{modifier_key} dict must include either "variable" or "code"',
    ),
    MessageId.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING: MessageDefinition(
        code="EG412",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Field modifier shorthand references a field not defined on this screen",
        template=(
            '{modifier_key}: "{variable}" is not defined on this screen. Use '
            "{modifier_key}: {{ code: ... }} instead for variables from previous screens"
        ),
    ),
    MessageId.FIELD_MODIFIER_CASE: MessageDefinition(
        code="EG413",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Invalid field modifier key casing",
        template=(
            'invalid field key "{field_key}". docassemble field modifier keys are '
            'case-sensitive; use "{suggested_key}"'
        ),
    ),
    MessageId.ACCESSIBILITY_COMBOBOX_NOT_ACCESSIBLE: MessageDefinition(
        code="EA501",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Combobox widget is not accessible",
        template="{subject} uses `combobox`, which is not allowed for accessibility reasons",
    ),
    MessageId.ACCESSIBILITY_NO_LABEL_MULTI_FIELD: MessageDefinition(
        code="EA502",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Field label is missing on a multi-field screen",
        template=(
            "`no label` or an empty/missing field label is only allowed on "
            "single-field screens; this screen has {field_count} fields: {field_name}"
        ),
    ),
    MessageId.ACCESSIBILITY_TAGGED_PDF_NOT_ENABLED: MessageDefinition(
        code="IA503",
        severity=Severity.INFO,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="DOCX attachment is missing tagged pdf",
        template=(
            "DOCX attachment detected without `tagged pdf: True`; set it on "
            "`features` or the attachment to improve generated PDF accessibility"
        ),
    ),
    MessageId.ACCESSIBILITY_THEME_CONTRAST_TOO_LOW: MessageDefinition(
        code="EA504",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Bootstrap theme CSS has low contrast",
        template=(
            "bootstrap theme CSS has low contrast for {component} "
            "(ratio {ratio:.2f}:1, expected at least {minimum_ratio:.1f}:1)"
        ),
    ),
    MessageId.ACCESSIBILITY_IMAGE_MISSING_ALT_TEXT: MessageDefinition(
        code="EA505",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Image is missing alt text",
        template="{image_kind} in {section_location} is missing alt text: {snippet}",
    ),
    MessageId.ACCESSIBILITY_MARKDOWN_HEADING_LEVEL_SKIP: MessageDefinition(
        code="EA506",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Markdown heading levels skip",
        template=(
            "markdown heading levels skip from H{previous_level} to H{current_level} "
            "in {section_location}: {snippet}"
        ),
    ),
    MessageId.ACCESSIBILITY_HTML_HEADING_LEVEL_SKIP: MessageDefinition(
        code="EA507",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="HTML heading levels skip",
        template=(
            "HTML heading levels skip from H{previous_level} to H{current_level} "
            "in {section_location}: {snippet}"
        ),
    ),
    MessageId.ACCESSIBILITY_EMPTY_LINK_TEXT: MessageDefinition(
        code="EA508",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Link has no accessible text",
        template="link in {section_location} has no accessible text: {snippet}",
    ),
    MessageId.ACCESSIBILITY_NON_DESCRIPTIVE_LINK_TEXT: MessageDefinition(
        code="EA509",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Link text is too generic",
        template="link text in {section_location} is too generic: {text}",
    ),
    MessageId.URL_CONCATENATED_ERROR: MessageDefinition(
        code="EG601",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Malformed URL text appears to contain another URL",
        template=(
            "malformed URL text appears to contain another URL in {source_label}: "
            "{url} (found in: {sources})"
        ),
    ),
    MessageId.URL_CONCATENATED_WARNING: MessageDefinition(
        code="WG601",
        severity=Severity.WARNING,
        finding_class=FindingClass.GENERAL,
        summary="Malformed URL text appears to contain another URL",
        template=(
            "malformed URL text appears to contain another URL in {source_label}: "
            "{url} (found in: {sources})"
        ),
    ),
    MessageId.URL_BROKEN_ERROR: MessageDefinition(
        code="EG602",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="URL returned HTTP 404/410",
        template=(
            "URL returned HTTP {status_code} in {source_label}: {url} "
            "(found in: {sources})"
        ),
    ),
    MessageId.URL_BROKEN_WARNING: MessageDefinition(
        code="WG602",
        severity=Severity.WARNING,
        finding_class=FindingClass.GENERAL,
        summary="URL returned HTTP 404/410",
        template=(
            "URL returned HTTP {status_code} in {source_label}: {url} "
            "(found in: {sources})"
        ),
    ),
    MessageId.URL_UNREACHABLE_ERROR: MessageDefinition(
        code="EG603",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="URL could not be reached",
        template=(
            "could not reach URL in {source_label} to verify it: {url} "
            "(found in: {sources})"
        ),
    ),
    MessageId.URL_UNREACHABLE_WARNING: MessageDefinition(
        code="WG603",
        severity=Severity.WARNING,
        finding_class=FindingClass.GENERAL,
        summary="URL could not be reached",
        template=(
            "could not reach URL in {source_label} to verify it: {url} "
            "(found in: {sources})"
        ),
    ),
}


def get_message_definition(message_id: str) -> MessageDefinition:
    return MESSAGE_DEFINITIONS[message_id]


def render_message(message_id: str, context: Mapping[str, Any]) -> str:
    return get_message_definition(message_id).template.format(**context)


@dataclass(frozen=True, slots=True)
class Finding:
    message_id: str
    file_name: str | None = None
    line_number: int | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    @property
    def definition(self) -> MessageDefinition:
        return get_message_definition(self.message_id)

    @property
    def code(self) -> str:
        return self.definition.code

    @property
    def severity(self) -> Severity:
        return self.definition.severity

    @property
    def finding_class(self) -> FindingClass:
        return self.definition.finding_class

    @property
    def summary(self) -> str:
        return self.definition.summary

    @property
    def message(self) -> str:
        return render_message(self.message_id, self.context)

    @property
    def err_str(self) -> str:
        return self.message

    def __str__(self) -> str:
        location = self.file_name or "<unknown>"
        if self.line_number is not None:
            location = f"{location}:{self.line_number}"
        return f"At {location}: [{self.code}] {self.message}"


@dataclass(frozen=True, slots=True)
class FindingDraft:
    message_id: str
    line_number: int = 1
    context: Mapping[str, Any] = field(default_factory=dict)

    @property
    def definition(self) -> MessageDefinition:
        return get_message_definition(self.message_id)

    @property
    def code(self) -> str:
        return self.definition.code

    @property
    def severity(self) -> Severity:
        return self.definition.severity

    @property
    def message(self) -> str:
        return render_message(self.message_id, self.context)

    def to_finding(self, *, file_name: str, line_number: int | None = None) -> Finding:
        return Finding(
            message_id=self.message_id,
            file_name=file_name,
            line_number=self.line_number if line_number is None else line_number,
            context=self.context,
        )


def draft(message_id: str, line_number: int = 1, **context: Any) -> FindingDraft:
    return FindingDraft(message_id=message_id, line_number=line_number, context=context)


def make_finding(
    message_id: str,
    *,
    file_name: str | None = None,
    line_number: int | None = None,
    **context: Any,
) -> Finding:
    return Finding(
        message_id=message_id,
        file_name=file_name,
        line_number=line_number,
        context=context,
    )
