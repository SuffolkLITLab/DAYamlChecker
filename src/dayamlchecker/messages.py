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
    STYLE = "style"
    TRANSLATABILITY = "translatability"


class MessageId(StrEnum):
    YAML_DUPLICATE_KEY = "yaml_duplicate_key"
    YAML_DUPLICATE_BLOCK_ID = "yaml_duplicate_block_id"
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
    OBJECTS_BLOCK_DICTIONARY = "objects_block_dictionary"
    FIELDS_CODE_TYPE = "fields_code_type"
    FIELDS_DICT_KEYS = "fields_dict_keys"
    FIELDS_TYPE = "fields_type"
    FIELD_MODIFIER_VARIABLE_TYPE = "field_modifier_variable_type"
    FIELD_MODIFIER_UNKNOWN_VARIABLE_DICT = "field_modifier_unknown_variable_dict"
    FIELD_MODIFIER_CODE_ERROR = "field_modifier_code_error"
    FIELD_MODIFIER_SAME_SCREEN_CODE = "field_modifier_same_screen_code"
    FIELD_MODIFIER_DICT_KEYS = "field_modifier_dict_keys"
    FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING = "field_modifier_unknown_variable_string"
    FIELD_MODIFIER_CASE = "field_modifier_case"
    MISSING_QUESTION_ID = "missing_question_id"
    MULTIPLE_MANDATORY_BLOCKS = "multiple_mandatory_blocks"
    MISSING_METADATA_FIELDS = "missing_metadata_fields"
    ATTACHMENT_CONDITIONAL_VARIABLE = "attachment_conditional_variable"

    ACCESSIBILITY_COMBOBOX_NOT_ACCESSIBLE = "accessibility_combobox_not_accessible"
    ACCESSIBILITY_NO_LABEL_MULTI_FIELD = "accessibility_no_label_multi_field"
    ACCESSIBILITY_TAGGED_PDF_NOT_ENABLED = "accessibility_tagged_pdf_not_enabled"
    ACCESSIBILITY_THEME_CONTRAST_TOO_LOW = "accessibility_theme_contrast_too_low"
    ACCESSIBILITY_IMAGE_MISSING_ALT_TEXT = "accessibility_image_missing_alt_text"
    ACCESSIBILITY_MARKDOWN_HEADING_LEVEL_SKIP = (
        "accessibility_markdown_heading_level_skip"
    )
    ACCESSIBILITY_HTML_HEADING_LEVEL_SKIP = "accessibility_html_heading_level_skip"
    ACCESSIBILITY_EMPTY_LINK_TEXT = "accessibility_empty_link_text"
    ACCESSIBILITY_NON_DESCRIPTIVE_LINK_TEXT = "accessibility_non_descriptive_link_text"
    ACCESSIBILITY_YESNO_SHORTCUT = "accessibility_yesno_shortcut"
    ACCESSIBILITY_FIELD_MISSING_LABEL = "accessibility_field_missing_label"
    ACCESSIBILITY_NON_DESCRIPTIVE_FIELD_LABEL = (
        "accessibility_non_descriptive_field_label"
    )
    ACCESSIBILITY_BLANK_CHOICE_LABEL = "accessibility_blank_choice_label"
    ACCESSIBILITY_NON_DESCRIPTIVE_CHOICE_LABEL = (
        "accessibility_non_descriptive_choice_label"
    )
    ACCESSIBILITY_DUPLICATE_FIELD_LABEL = "accessibility_duplicate_field_label"
    ACCESSIBILITY_COLOR_ONLY_INSTRUCTIONS = "accessibility_color_only_instructions"
    ACCESSIBILITY_INLINE_COLOR_STYLING = "accessibility_inline_color_styling"
    ACCESSIBILITY_AMBIGUOUS_LINK_DESTINATIONS = (
        "accessibility_ambiguous_link_destinations"
    )
    ACCESSIBILITY_NEW_TAB_WITHOUT_WARNING = "accessibility_new_tab_without_warning"
    ACCESSIBILITY_SVG_MISSING_ACCESSIBLE_NAME = (
        "accessibility_svg_missing_accessible_name"
    )
    ACCESSIBILITY_TABLE_MISSING_HEADERS = "accessibility_table_missing_headers"
    ACCESSIBILITY_LAYOUT_TABLE_NEEDS_REVIEW = "accessibility_layout_table_needs_review"
    ACCESSIBILITY_POSITIVE_TABINDEX = "accessibility_positive_tabindex"
    ACCESSIBILITY_CLICKABLE_NON_CONTROL_HTML = (
        "accessibility_clickable_non_control_html"
    )
    ACCESSIBILITY_REQUIRED_FIELD_NOT_INDICATED = (
        "accessibility_required_field_not_indicated"
    )
    ACCESSIBILITY_VALIDATION_WITHOUT_GUIDANCE = (
        "accessibility_validation_without_guidance"
    )
    ACCESSIBILITY_GENERIC_VALIDATION_MESSAGE = (
        "accessibility_generic_validation_message"
    )
    ACCESSIBILITY_AMBIGUOUS_BUTTON_TEXT = "accessibility_ambiguous_button_text"

    # Translatability
    TRANSLATABILITY_CHOICES_WITHOUT_STABLE_VALUES = (
        "translatability_choices_without_stable_values"
    )
    TRANSLATABILITY_HARDCODED_USER_TEXT_IN_CODE = (
        "translatability_hardcoded_user_text_in_code"
    )
    TRANSLATABILITY_TERNARY_CONDITIONAL_TEXT = (
        "translatability_ternary_conditional_text"
    )
    TRANSLATABILITY_CONDITIONAL_SENTENCE_FRAGMENT = (
        "translatability_conditional_sentence_fragment"
    )

    STYLE_SUBQUESTION_H1 = "style_subquestion_h1"
    STYLE_REMOVE_LANGUAGE_EN = "style_remove_language_en"
    STYLE_MISSING_SCREEN_TITLE = "style_missing_screen_title"
    STYLE_PLACEHOLDER_LANGUAGE = "style_placeholder_language"
    STYLE_PLAIN_LANGUAGE_REPLACEMENT = "style_plain_language_replacement"
    STYLE_VARIABLE_ROOT_NOT_SNAKE_CASE = "style_variable_root_not_snake_case"
    STYLE_LONG_SENTENCE = "style_long_sentence"
    STYLE_COMPOUND_QUESTION = "style_compound_question"
    STYLE_OVERLONG_QUESTION_LABEL = "style_overlong_question_label"
    STYLE_OVERLONG_FIELD_LABEL = "style_overlong_field_label"
    STYLE_TOO_MANY_FIELDS_ON_SCREEN = "style_too_many_fields_on_screen"
    STYLE_WALL_OF_TEXT = "style_wall_of_text"
    STYLE_COMPLEX_SCREEN_MISSING_HELP = "style_complex_screen_missing_help"
    STYLE_MISSING_EXIT_CRITERIA_SCREEN = "style_missing_exit_criteria_screen"
    STYLE_MISSING_CUSTOM_THEME = "style_missing_custom_theme"
    STYLE_REVIEW_SCREEN_MISSING_EDIT_LINKS = "style_review_screen_missing_edit_links"
    STYLE_REVIEW_SCREEN_MISSING_KEY_CHOICE_EDITS = (
        "style_review_screen_missing_key_choice_edits"
    )
    STYLE_PREFER_PERSON_OBJECTS = "style_prefer_person_objects"
    STYLE_QUESTION_LEVEL_HELP = "style_question_level_help"
    STYLE_CONTRACTION = "style_contraction"
    STYLE_SLASH_ALTERNATIVE = "style_slash_alternative"
    STYLE_FIELD_LABEL_INSTRUCTION_VERB = "style_field_label_instruction_verb"
    STYLE_TITLE_CASE_LABEL = "style_title_case_label"
    STYLE_OTHER_CHOICE_NOT_LAST = "style_other_choice_not_last"
    STYLE_LANGUAGE_DROPDOWN = "style_language_dropdown"
    STYLE_LANGUAGE_CHOICE_VALUE = "style_language_choice_value"
    STYLE_PREFERRED_PRONOUNS = "style_preferred_pronouns"
    STYLE_GENDER_OTHER_CHOICE = "style_gender_other_choice"
    STYLE_GENDER_BINARY_ONLY = "style_gender_binary_only"
    STYLE_REQUIRED_PRONOUN_FIELD = "style_required_pronoun_field"
    STYLE_TONE_AND_RESPECT = "style_tone_and_respect"
    STYLE_PLAIN_LANGUAGE_REWRITE_OPPORTUNITY = (
        "style_plain_language_rewrite_opportunity"
    )
    STYLE_LLM_CONFIGURATION_ERROR = "style_llm_configuration_error"
    STYLE_LLM_REQUEST_FAILED = "style_llm_request_failed"

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
    MessageId.YAML_DUPLICATE_BLOCK_ID: MessageDefinition(
        code="EG104",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Duplicate block id",
        template='Duplicate block id "{block_id}" - first used at line {first_line}. Docassemble will silently use the later block, which is almost certainly a mistake',
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
            "Use val(\"...\") or val('...') instead"
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
    MessageId.OBJECTS_BLOCK_DICTIONARY: MessageDefinition(
        code="EG417",
        severity=Severity.WARNING,
        finding_class=FindingClass.GENERAL,
        summary="objects block should be a list instead of a dict",
        template="objects block should be a list instead of a dict",
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
    MessageId.MISSING_QUESTION_ID: MessageDefinition(
        code="EG414",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Question block is missing an id",
        template="question block is missing an `id`: {snippet}",
    ),
    MessageId.MULTIPLE_MANDATORY_BLOCKS: MessageDefinition(
        code="EG415",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Interview has more than one mandatory block",
        template="interview has more than one `mandatory: True` block: {labels}",
    ),
    MessageId.MISSING_METADATA_FIELDS: MessageDefinition(
        code="IG416",
        severity=Severity.INFO,
        finding_class=FindingClass.GENERAL,
        summary="Metadata block is missing common CourtFormsOnline fields",
        template=(
            "metadata block is missing common CourtFormsOnline publishing fields: "
            "{fields}"
        ),
    ),
    MessageId.ATTACHMENT_CONDITIONAL_VARIABLE: MessageDefinition(
        code="EG416",
        severity=Severity.ERROR,
        finding_class=FindingClass.GENERAL,
        summary="Attachment content references a conditionally asked variable",
        template='attachment content references "{field_var}", but that field is only asked when certain conditions are met (show if/hide if). If those conditions are not met, the interview may get stuck',
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
    MessageId.ACCESSIBILITY_YESNO_SHORTCUT: MessageDefinition(
        code="EA510",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Question uses yesno shorthand",
        template="screen uses `{shortcut}` question shorthand; prefer `fields` with an explicit datatype",
    ),
    MessageId.ACCESSIBILITY_FIELD_MISSING_LABEL: MessageDefinition(
        code="EA511",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Field appears to have no visible label",
        template="field appears to collect user input but has no visible label: {field_name}",
    ),
    MessageId.ACCESSIBILITY_NON_DESCRIPTIVE_FIELD_LABEL: MessageDefinition(
        code="WA512",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Field label may be too vague",
        template="field label may be too vague for assistive technology users: {snippet}",
    ),
    MessageId.ACCESSIBILITY_BLANK_CHOICE_LABEL: MessageDefinition(
        code="EA513",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Choice label is blank",
        template="choice label is blank in {location}",
    ),
    MessageId.ACCESSIBILITY_NON_DESCRIPTIVE_CHOICE_LABEL: MessageDefinition(
        code="WA514",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Choice label may be too vague",
        template="choice label in {location} may be too vague: {snippet}",
    ),
    MessageId.ACCESSIBILITY_DUPLICATE_FIELD_LABEL: MessageDefinition(
        code="WA515",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Multiple fields share the same label",
        template="multiple fields on this screen share the same label text: {labels}",
    ),
    MessageId.ACCESSIBILITY_COLOR_ONLY_INSTRUCTIONS: MessageDefinition(
        code="WA516",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Text may rely on color or symbols alone",
        template="text in {section_location} may rely on color or symbols alone to convey meaning: {snippet}",
    ),
    MessageId.ACCESSIBILITY_INLINE_COLOR_STYLING: MessageDefinition(
        code="WA517",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Text uses inline or semantic color styling",
        template="text in {section_location} uses inline or semantic color styling; verify contrast and non-color cues: {snippet}",
    ),
    MessageId.ACCESSIBILITY_AMBIGUOUS_LINK_DESTINATIONS: MessageDefinition(
        code="WA518",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Same link text points to multiple destinations",
        template="same link text points to multiple destinations on this screen: {snippet}",
    ),
    MessageId.ACCESSIBILITY_NEW_TAB_WITHOUT_WARNING: MessageDefinition(
        code="WA519",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Link opens a new tab without warning text",
        template="link in {section_location} opens a new tab or window without warning text: {snippet}",
    ),
    MessageId.ACCESSIBILITY_SVG_MISSING_ACCESSIBLE_NAME: MessageDefinition(
        code="WA520",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Inline SVG is missing an accessible name",
        template="inline SVG in {section_location} is missing a title or ARIA label: {snippet}",
    ),
    MessageId.ACCESSIBILITY_TABLE_MISSING_HEADERS: MessageDefinition(
        code="EA521",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Table appears to need header cells",
        template="table in {section_location} appears to be data but has no `<th>` headers: {snippet}",
    ),
    MessageId.ACCESSIBILITY_LAYOUT_TABLE_NEEDS_REVIEW: MessageDefinition(
        code="WA522",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Table needs review for layout-only usage",
        template="table in {section_location} has no headers or caption; confirm it is not layout-only: {snippet}",
    ),
    MessageId.ACCESSIBILITY_POSITIVE_TABINDEX: MessageDefinition(
        code="EA523",
        severity=Severity.ERROR,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Positive tabindex disrupts focus order",
        template="HTML in {section_location} uses `tabindex` greater than 0: {snippet}",
    ),
    MessageId.ACCESSIBILITY_CLICKABLE_NON_CONTROL_HTML: MessageDefinition(
        code="WA524",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Clickable non-control element may lack keyboard support",
        template="`<{tag_name}>` in {section_location} uses `onclick` without clear keyboard semantics: {snippet}",
    ),
    MessageId.ACCESSIBILITY_REQUIRED_FIELD_NOT_INDICATED: MessageDefinition(
        code="WA525",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Required field may not be indicated clearly",
        template="required field may not clearly indicate that it is required: {snippet}",
    ),
    MessageId.ACCESSIBILITY_VALIDATION_WITHOUT_GUIDANCE: MessageDefinition(
        code="WA526",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Inline custom validation lacks a validation message",
        template="field uses inline custom validation without a clear validation message: {snippet}",
    ),
    MessageId.ACCESSIBILITY_GENERIC_VALIDATION_MESSAGE: MessageDefinition(
        code="WA527",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Validation message may be too generic",
        template="validation message may be too generic to help users recover: {snippet}",
    ),
    MessageId.ACCESSIBILITY_AMBIGUOUS_BUTTON_TEXT: MessageDefinition(
        code="WA528",
        severity=Severity.WARNING,
        finding_class=FindingClass.ACCESSIBILITY,
        summary="Button text may be too vague",
        template="button text may be too vague out of context: {snippet}",
    ),
    # Translatability
    MessageId.TRANSLATABILITY_CHOICES_WITHOUT_STABLE_VALUES: MessageDefinition(
        code="WT701",
        severity=Severity.WARNING,
        finding_class=FindingClass.TRANSLATABILITY,
        summary="Choices are missing invariant values",
        template=(
            "{origin} includes labels without explicit invariant values; translated "
            "labels should not be stored as answers: {snippet}"
        ),
    ),
    MessageId.TRANSLATABILITY_HARDCODED_USER_TEXT_IN_CODE: MessageDefinition(
        code="WT702",
        severity=Severity.WARNING,
        finding_class=FindingClass.TRANSLATABILITY,
        summary="User-facing text appears inside a code block",
        template=(
            "move user-facing text out of `code:` blocks and into a translatable "
            "template: {snippet}"
        ),
    ),
    MessageId.TRANSLATABILITY_TERNARY_CONDITIONAL_TEXT: MessageDefinition(
        code="WT703",
        severity=Severity.WARNING,
        finding_class=FindingClass.TRANSLATABILITY,
        summary="Ternary conditional text may not be translatable",
        template=(
            "ternary conditional text in {location} may not be extracted for "
            "translation; use a Mako conditional block around each full sentence: "
            "{snippet}"
        ),
    ),
    MessageId.TRANSLATABILITY_CONDITIONAL_SENTENCE_FRAGMENT: MessageDefinition(
        code="WT704",
        severity=Severity.WARNING,
        finding_class=FindingClass.TRANSLATABILITY,
        summary="Conditional text changes only part of a sentence",
        template=(
            "Mako conditional in {location} appears to change only part of a "
            "sentence; put each full sentence inside a conditional branch: {snippet}"
        ),
    ),
    MessageId.STYLE_SUBQUESTION_H1: MessageDefinition(
        code="ES701",
        severity=Severity.ERROR,
        finding_class=FindingClass.STYLE,
        summary="Subquestion contains an H1 heading",
        template="subquestion contains an H1 heading; use H2+ inside body text: {snippet}",
    ),
    MessageId.STYLE_REMOVE_LANGUAGE_EN: MessageDefinition(
        code="ES703",
        severity=Severity.ERROR,
        finding_class=FindingClass.STYLE,
        summary="Explicit language: en is unnecessary",
        template="remove `language: en`; English is the default in docassemble interviews",
    ),
    MessageId.STYLE_MISSING_SCREEN_TITLE: MessageDefinition(
        code="WS710",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Screen is missing a meaningful title",
        template="screen appears to have user-facing content but no meaningful `question`: {snippet}",
    ),
    MessageId.STYLE_PLACEHOLDER_LANGUAGE: MessageDefinition(
        code="WS711",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Placeholder language detected",
        template="placeholder language appears in {location}: {snippet}",
    ),
    MessageId.STYLE_PLAIN_LANGUAGE_REPLACEMENT: MessageDefinition(
        code="IS712",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Prefer a plainer word or phrase",
        template=(
            "consider replacing {matched_text!r} in {location} with simpler language, "
            "such as {replacement!r}"
        ),
    ),
    MessageId.STYLE_VARIABLE_ROOT_NOT_SNAKE_CASE: MessageDefinition(
        code="WS713",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Variable roots should use snake_case",
        template="variable roots should use snake_case: {roots}",
    ),
    MessageId.STYLE_LONG_SENTENCE: MessageDefinition(
        code="WS714",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Sentence is probably too long",
        template="sentence in {location} exceeds 20 words: {snippet}",
    ),
    MessageId.STYLE_COMPOUND_QUESTION: MessageDefinition(
        code="IS715",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Question may ask about more than one thing",
        template="potential compound question in {location}: {snippet}",
    ),
    MessageId.STYLE_OVERLONG_QUESTION_LABEL: MessageDefinition(
        code="WS716",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Question title is probably too long",
        template="question text exceeds 120 characters: {snippet}",
    ),
    MessageId.STYLE_OVERLONG_FIELD_LABEL: MessageDefinition(
        code="WS717",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Field label is probably too long",
        template="field label exceeds 90 characters: {snippet}",
    ),
    MessageId.STYLE_TOO_MANY_FIELDS_ON_SCREEN: MessageDefinition(
        code="WS718",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Screen contains too many fields",
        template="screen contains {field_count} fields; consider splitting it into smaller steps",
    ),
    MessageId.STYLE_WALL_OF_TEXT: MessageDefinition(
        code="WS719",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Subquestion may be a wall of text",
        template="subquestion has a long unstructured block of text: {snippet}",
    ),
    MessageId.STYLE_COMPLEX_SCREEN_MISSING_HELP: MessageDefinition(
        code="IS720",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Complex screen has no inline help",
        template="complex screen has no help, hint, or note text: {snippet}",
    ),
    MessageId.STYLE_MISSING_EXIT_CRITERIA_SCREEN: MessageDefinition(
        code="IS721",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Eligibility screening may need an exit screen",
        template=(
            "interview appears to screen for eligibility but no clear ineligible or exit screen was detected"
        ),
    ),
    MessageId.STYLE_MISSING_CUSTOM_THEME: MessageDefinition(
        code="IS722",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Root interview may be missing a custom theme",
        template=(
            "metadata suggests a root interview file, but no explicit custom theme or CSS dependency was detected"
        ),
    ),
    MessageId.STYLE_REVIEW_SCREEN_MISSING_EDIT_LINKS: MessageDefinition(
        code="WS723",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Review screen has no edit links",
        template="review screen detected but no editable `Edit:` links were found",
    ),
    MessageId.STYLE_REVIEW_SCREEN_MISSING_KEY_CHOICE_EDITS: MessageDefinition(
        code="IS724",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Review screen may not edit key decision fields",
        template="review screen exists but does not appear to allow editing key decision fields: {snippet}",
    ),
    MessageId.STYLE_PREFER_PERSON_OBJECTS: MessageDefinition(
        code="IS725",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Interview may benefit from person objects",
        template="interview appears to use disconnected name or address variables; prefer ALIndividual or ALPeopleList patterns: {snippet}",
    ),
    MessageId.STYLE_QUESTION_LEVEL_HELP: MessageDefinition(
        code="WS726",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Question-level help is not recommended",
        template=(
            "avoid `help:` as a question modifier; use `collapse_template()` in "
            "`subquestion` or another inline pattern instead: {snippet}"
        ),
    ),
    MessageId.STYLE_CONTRACTION: MessageDefinition(
        code="WS727",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Avoid contractions in user-facing text",
        template="write out the contraction {matched_text!r} in {location}",
    ),
    MessageId.STYLE_SLASH_ALTERNATIVE: MessageDefinition(
        code="WS728",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Avoid slash-separated alternatives",
        template="write out slash-separated alternatives in {location}: {snippet}",
    ),
    MessageId.STYLE_FIELD_LABEL_INSTRUCTION_VERB: MessageDefinition(
        code="WS729",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Field label starts with an unnecessary instruction verb",
        template="field label can usually omit instruction verbs like enter, write, or list: {snippet}",
    ),
    MessageId.STYLE_TITLE_CASE_LABEL: MessageDefinition(
        code="IS730",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Prefer sentence case for headings and field labels",
        template="heading or label appears to use title case; prefer sentence case: {snippet}",
    ),
    MessageId.STYLE_OTHER_CHOICE_NOT_LAST: MessageDefinition(
        code="IS731",
        severity=Severity.INFO,
        finding_class=FindingClass.STYLE,
        summary="Put Other at the end of choice lists",
        template='choice list includes "Other" before the final option in {origin}',
    ),
    MessageId.STYLE_LANGUAGE_DROPDOWN: MessageDefinition(
        code="WS732",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Language choices should usually use radio buttons",
        template="language field appears to use a dropdown; use radio buttons for short language lists: {snippet}",
    ),
    MessageId.STYLE_LANGUAGE_CHOICE_VALUE: MessageDefinition(
        code="WS733",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Language choices should store ISO language codes",
        template="language choice should usually store a 2- or 3-letter ISO code: {snippet}",
    ),
    MessageId.STYLE_PREFERRED_PRONOUNS: MessageDefinition(
        code="WS734",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary='Use "Pronouns", not "preferred pronouns"',
        template='avoid "preferred pronouns" in {location}; use "Pronouns": {snippet}',
    ),
    MessageId.STYLE_GENDER_OTHER_CHOICE: MessageDefinition(
        code="WS735",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary='Avoid "Other" as a gender choice',
        template='gender choices should avoid "Other"; use an inclusive self-described option: {snippet}',
    ),
    MessageId.STYLE_GENDER_BINARY_ONLY: MessageDefinition(
        code="WS736",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Gender choices appear to be binary only",
        template="gender field appears to offer only Female and Male choices: {snippet}",
    ),
    MessageId.STYLE_REQUIRED_PRONOUN_FIELD: MessageDefinition(
        code="WS737",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Pronoun fields should usually be optional",
        template="pronoun field appears to be required; pronouns should usually be optional: {snippet}",
    ),
    MessageId.STYLE_TONE_AND_RESPECT: MessageDefinition(
        code="WS790",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Potential tone or respect issue",
        template="{message}",
    ),
    MessageId.STYLE_PLAIN_LANGUAGE_REWRITE_OPPORTUNITY: MessageDefinition(
        code="WS791",
        severity=Severity.WARNING,
        finding_class=FindingClass.STYLE,
        summary="Potential plain-language rewrite opportunity",
        template="{message}",
    ),
    MessageId.STYLE_LLM_CONFIGURATION_ERROR: MessageDefinition(
        code="ES792",
        severity=Severity.ERROR,
        finding_class=FindingClass.STYLE,
        summary="Style LLM checks are misconfigured",
        template="{detail}",
    ),
    MessageId.STYLE_LLM_REQUEST_FAILED: MessageDefinition(
        code="ES793",
        severity=Severity.ERROR,
        finding_class=FindingClass.STYLE,
        summary="Style LLM request failed",
        template='LLM-backed style rule "{rule_id}" could not run: {detail}',
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
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
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
        severity_label = {
            Severity.ERROR: "ERROR",
            Severity.WARNING: "WARN",
            Severity.INFO: "INFO",
        }[self.severity]
        indented_message = "\n".join(f"  {line}" for line in self.message.splitlines())
        return f"{severity_label:<5} [{self.code}] {location}\n" f"{indented_message}"


@dataclass(frozen=True, slots=True)
class FindingDraft:
    message_id: str
    line_number: int = 1
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
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
            column=self.column,
            end_line=self.end_line,
            end_column=self.end_column,
            context=self.context,
        )


def draft(message_id: str, line_number: int = 1, **context: Any) -> FindingDraft:
    return FindingDraft(message_id=message_id, line_number=line_number, context=context)


def make_finding(
    message_id: str,
    *,
    file_name: str | None = None,
    line_number: int | None = None,
    column: int | None = None,
    end_line: int | None = None,
    end_column: int | None = None,
    **context: Any,
) -> Finding:
    return Finding(
        message_id=message_id,
        file_name=file_name,
        line_number=line_number,
        column=column,
        end_line=end_line,
        end_column=end_column,
        context=context,
    )


def escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(value: str) -> str:
    return escape_data(value).replace(":", "%3A").replace(",", "%2C")


def print_github_annotation(d: Finding) -> None:
    kind = "notice" if d.severity == Severity.INFO else d.severity.value

    props = []

    if getattr(d, "file_name", None):
        props.append(f"file={escape_property(str(d.file_name))}")
    if getattr(d, "line_number", None):
        props.append(f"line={d.line_number}")
    if d.column is not None:
        props.append(f"col={d.column}")
    if d.end_line is not None:
        props.append(f"endLine={d.end_line}")
    if d.end_column is not None:
        props.append(f"endColumn={d.end_column}")
    if getattr(d, "code", None):
        props.append(f"title={escape_property(d.code)}")

    prop_text = ",".join(props)
    message = escape_data(d.message)

    if prop_text:
        print(f"::{kind} {prop_text}::{message}")
    else:
        print(f"::{kind}::{message}")
