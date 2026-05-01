from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class MessageDefinition:
    code: str
    summary: str
    template: str
    experimental: bool = True


class MessageCode(StrEnum):
    YAML_DUPLICATE_KEY = "E101"
    YAML_PARSE_ERROR = "E102"
    JINJA2_SYNTAX_ERROR = "E201"
    JINJA2_TEMPLATE_ERROR = "E202"
    UNKNOWN_KEYS = "E301"

    YAML_STRING_TYPE = "W101"
    MAKO_SYNTAX_ERROR = "W111"
    MAKO_COMPILE_ERROR = "W112"
    PYTHON_CODE_TYPE = "W121"
    PYTHON_SYNTAX_ERROR = "W122"

    JS_MODIFIER_TYPE = "W201"
    JS_INVALID_SYNTAX = "W202"
    JS_MISSING_VAL_CALL = "W203"
    JS_UNKNOWN_SCREEN_FIELD = "W204"
    JS_VAL_ARG_NOT_QUOTED = "W205"

    SHOW_IF_MALFORMED = "W301"
    SHOW_IF_CODE_TYPE = "W302"
    SHOW_IF_CODE_SYNTAX = "W303"
    SHOW_IF_DICT_KEYS = "W304"

    PYTHON_VAR_TYPE = "W401"
    PYTHON_VAR_WHITESPACE = "W402"
    OBJECTS_BLOCK_TYPE = "W403"
    FIELDS_CODE_TYPE = "W404"
    FIELDS_DICT_KEYS = "W405"
    FIELDS_TYPE = "W406"
    FIELD_MODIFIER_VARIABLE_TYPE = "W407"
    FIELD_MODIFIER_UNKNOWN_VARIABLE_DICT = "W408"
    FIELD_MODIFIER_CODE_ERROR = "W409"
    FIELD_MODIFIER_SAME_SCREEN_CODE = "W410"
    FIELD_MODIFIER_DICT_KEYS = "W411"
    FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING = "W412"

    NO_POSSIBLE_TYPES = "W601"
    TOO_MANY_TYPES = "W602"
    INTERVIEW_ORDER_UNMATCHED_GUARD = "W603"
    NESTED_VISIBILITY_LOGIC = "W604"

    ACCESSIBILITY_COMBOBOX_NOT_ACCESSIBLE = "E501"
    ACCESSIBILITY_NO_LABEL_MULTI_FIELD = "E502"
    ACCESSIBILITY_TAGGED_PDF_NOT_ENABLED = "E503"
    ACCESSIBILITY_THEME_CONTRAST_TOO_LOW = "E504"
    ACCESSIBILITY_IMAGE_MISSING_ALT_TEXT = "E505"
    ACCESSIBILITY_MARKDOWN_HEADING_LEVEL_SKIP = "E506"
    ACCESSIBILITY_HTML_HEADING_LEVEL_SKIP = "E507"
    ACCESSIBILITY_EMPTY_LINK_TEXT = "E508"
    ACCESSIBILITY_NON_DESCRIPTIVE_LINK_TEXT = "E509"

    VALIDATION_CODE_MISSING_VALIDATION_ERROR = "C101"


MESSAGE_DEFINITIONS: dict[str, MessageDefinition] = {
    MessageCode.YAML_DUPLICATE_KEY: MessageDefinition(
        code=MessageCode.YAML_DUPLICATE_KEY,
        summary="Duplicate YAML key",
        template="duplicate key '{key_name}'",
        experimental=False,
    ),
    MessageCode.YAML_PARSE_ERROR: MessageDefinition(
        code=MessageCode.YAML_PARSE_ERROR,
        summary="YAML parsing error",
        template="{error}",
        experimental=False,
    ),
    MessageCode.JINJA2_SYNTAX_ERROR: MessageDefinition(
        code=MessageCode.JINJA2_SYNTAX_ERROR,
        summary="Jinja2 syntax error",
        template="Jinja2 syntax error at line {line_number}: {message}",
        experimental=False,
    ),
    MessageCode.JINJA2_TEMPLATE_ERROR: MessageDefinition(
        code=MessageCode.JINJA2_TEMPLATE_ERROR,
        summary="Jinja2 template error",
        template="Jinja2 template error: {error}",
        experimental=False,
    ),
    MessageCode.UNKNOWN_KEYS: MessageDefinition(
        code=MessageCode.UNKNOWN_KEYS,
        summary="Unknown YAML keys",
        template="Keys that shouldn't exist! {keys}",
        experimental=False,
    ),
    MessageCode.YAML_STRING_TYPE: MessageDefinition(
        code=MessageCode.YAML_STRING_TYPE,
        summary="Expected YAML string",
        template="{value} isn't a string",
    ),
    MessageCode.MAKO_SYNTAX_ERROR: MessageDefinition(
        code=MessageCode.MAKO_SYNTAX_ERROR,
        summary="Invalid Mako syntax",
        template="{error}",
    ),
    MessageCode.MAKO_COMPILE_ERROR: MessageDefinition(
        code=MessageCode.MAKO_COMPILE_ERROR,
        summary="Mako compile error",
        template="{error}",
    ),
    MessageCode.PYTHON_CODE_TYPE: MessageDefinition(
        code=MessageCode.PYTHON_CODE_TYPE,
        summary="Expected Python code as YAML string",
        template="code block must be a YAML string, is {value_type}",
    ),
    MessageCode.PYTHON_SYNTAX_ERROR: MessageDefinition(
        code=MessageCode.PYTHON_SYNTAX_ERROR,
        summary="Python syntax error",
        template="Python syntax error: {message}",
    ),
    MessageCode.JS_MODIFIER_TYPE: MessageDefinition(
        code=MessageCode.JS_MODIFIER_TYPE,
        summary="JavaScript modifier must be string",
        template="{modifier_key} must be a string, is {value_type}",
    ),
    MessageCode.JS_INVALID_SYNTAX: MessageDefinition(
        code=MessageCode.JS_INVALID_SYNTAX,
        summary="Invalid JavaScript syntax",
        template="Invalid JavaScript syntax in {modifier_key}: {error}",
    ),
    MessageCode.JS_MISSING_VAL_CALL: MessageDefinition(
        code=MessageCode.JS_MISSING_VAL_CALL,
        summary="Missing val() call in JavaScript modifier",
        template="{modifier_key} must contain at least one val() call to reference an on-screen field",
    ),
    MessageCode.JS_UNKNOWN_SCREEN_FIELD: MessageDefinition(
        code=MessageCode.JS_UNKNOWN_SCREEN_FIELD,
        summary="val() references field not defined on this screen",
        template='{modifier_key} references val("{var_name}"), but "{var_name}" is not defined on this screen{caveat}',
    ),
    MessageCode.JS_VAL_ARG_NOT_QUOTED: MessageDefinition(
        code=MessageCode.JS_VAL_ARG_NOT_QUOTED,
        summary="val() argument must be quoted string literal",
        template='val() argument must be a quoted string literal, not "{bad_arg}". Use val("...") or val(\'...\') instead',
    ),
    MessageCode.SHOW_IF_MALFORMED: MessageDefinition(
        code=MessageCode.SHOW_IF_MALFORMED,
        summary="Malformed show if shorthand",
        template='show if value "{value}" appears to be malformed. Use YAML dict syntax: show if: {{ variable: var_name, is: value }} or show if: {{ code: ... }}',
    ),
    MessageCode.SHOW_IF_CODE_TYPE: MessageDefinition(
        code=MessageCode.SHOW_IF_CODE_TYPE,
        summary="show if code must be YAML string",
        template="show if: code must be a YAML string",
    ),
    MessageCode.SHOW_IF_CODE_SYNTAX: MessageDefinition(
        code=MessageCode.SHOW_IF_CODE_SYNTAX,
        summary="show if code has Python syntax error",
        template="show if: code has Python syntax error: {message}",
    ),
    MessageCode.SHOW_IF_DICT_KEYS: MessageDefinition(
        code=MessageCode.SHOW_IF_DICT_KEYS,
        summary="show if dict missing variable/code",
        template='show if dict must have either "variable" key or "code" key',
    ),
    MessageCode.PYTHON_VAR_TYPE: MessageDefinition(
        code=MessageCode.PYTHON_VAR_TYPE,
        summary="Python variable reference must be YAML string",
        template="The python var needs to be a YAML string, is {value}",
    ),
    MessageCode.PYTHON_VAR_WHITESPACE: MessageDefinition(
        code=MessageCode.PYTHON_VAR_WHITESPACE,
        summary="Python variable reference cannot contain whitespace",
        template="The python var cannot have whitespace (is {value})",
    ),
    MessageCode.OBJECTS_BLOCK_TYPE: MessageDefinition(
        code=MessageCode.OBJECTS_BLOCK_TYPE,
        summary="Objects block must be list or dict",
        template="Objects block needs to be a list or a dict, is {value}",
    ),
    MessageCode.FIELDS_CODE_TYPE: MessageDefinition(
        code=MessageCode.FIELDS_CODE_TYPE,
        summary="fields code must be YAML string",
        template="fields: code must be a YAML string, is {value_type}",
    ),
    MessageCode.FIELDS_DICT_KEYS: MessageDefinition(
        code=MessageCode.FIELDS_DICT_KEYS,
        summary="fields dict has no recognized field or code key",
        template='fields dict must have a recognized field key or "code" key, is {value}',
    ),
    MessageCode.FIELDS_TYPE: MessageDefinition(
        code=MessageCode.FIELDS_TYPE,
        summary="fields must be list or dict",
        template="fields should be a list or dict, is {value}",
    ),
    MessageCode.FIELD_MODIFIER_VARIABLE_TYPE: MessageDefinition(
        code=MessageCode.FIELD_MODIFIER_VARIABLE_TYPE,
        summary="field modifier variable must be string",
        template="{modifier_key}: variable must be a string, got {value_type}",
    ),
    MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_DICT: MessageDefinition(
        code=MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_DICT,
        summary="field modifier variable references off-screen field",
        template="{modifier_key}: variable: {ref_var} is not defined on this screen. Use {modifier_key}: {{ code: ... }} instead for variables from previous screens",
    ),
    MessageCode.FIELD_MODIFIER_CODE_ERROR: MessageDefinition(
        code=MessageCode.FIELD_MODIFIER_CODE_ERROR,
        summary="field modifier code has validation error",
        template="{modifier_key}: code has {error}",
    ),
    MessageCode.FIELD_MODIFIER_SAME_SCREEN_CODE: MessageDefinition(
        code=MessageCode.FIELD_MODIFIER_SAME_SCREEN_CODE,
        summary="show if code references same-screen field",
        template="{modifier_key}: code references variable(s) defined on this screen ({references}). Use {modifier_key}: <var> or {modifier_key}: {{ variable: <var>, is: ... }} instead",
    ),
    MessageCode.FIELD_MODIFIER_DICT_KEYS: MessageDefinition(
        code=MessageCode.FIELD_MODIFIER_DICT_KEYS,
        summary="field modifier dict missing variable/code",
        template='{modifier_key} dict must have either "variable" or "code"',
    ),
    MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING: MessageDefinition(
        code=MessageCode.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING,
        summary="field modifier shorthand references off-screen field",
        template="{modifier_key}: {modifier_value} is not defined on this screen. Use {modifier_key}: {{ code: ... }} instead for variables from previous screens",
    ),
    MessageCode.NO_POSSIBLE_TYPES: MessageDefinition(
        code=MessageCode.NO_POSSIBLE_TYPES,
        summary="No recognized block type found",
        template="Couldn't identify a block type: no valid combination of keys found (looking for keys like question, include, metadata, code, objects, etc. See https://docassemble.org/docs.html)",
    ),
    MessageCode.TOO_MANY_TYPES: MessageDefinition(
        code=MessageCode.TOO_MANY_TYPES,
        summary="Block matches multiple exclusive types",
        template="Too many types this block could be: {possible_types}",
    ),
    MessageCode.INTERVIEW_ORDER_UNMATCHED_GUARD: MessageDefinition(
        code=MessageCode.INTERVIEW_ORDER_UNMATCHED_GUARD,
        summary="Interview-order block missing matching guard",
        template='interview-order style block references "{field_var}" without a matching guard for that field\'s show/hide logic; this can cause the interview to get stuck',
    ),
    MessageCode.NESTED_VISIBILITY_LOGIC: MessageDefinition(
        code=MessageCode.NESTED_VISIBILITY_LOGIC,
        summary="Visibility logic is nested too deeply",
        template="Warning: show if/hide if visibility logic is nested {depth} levels on this screen (more than 2)",
    ),
    MessageCode.ACCESSIBILITY_COMBOBOX_NOT_ACCESSIBLE: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_COMBOBOX_NOT_ACCESSIBLE,
        summary="Combobox widget is not accessible",
        template="Accessibility: combobox widgets are not allowed for accessibility reasons",
    ),
    MessageCode.ACCESSIBILITY_NO_LABEL_MULTI_FIELD: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_NO_LABEL_MULTI_FIELD,
        summary="Field label missing on multi-field screen",
        template="Accessibility: no label or empty/missing field label is only allowed on single-field screens",
    ),
    MessageCode.ACCESSIBILITY_TAGGED_PDF_NOT_ENABLED: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_TAGGED_PDF_NOT_ENABLED,
        summary="DOCX attachment may need tagged PDF enabled",
        template="Accessibility: DOCX attachment detected without tagged pdf enabled",
    ),
    MessageCode.ACCESSIBILITY_THEME_CONTRAST_TOO_LOW: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_THEME_CONTRAST_TOO_LOW,
        summary="Bootstrap theme CSS has low contrast",
        template="Accessibility: bootstrap theme CSS has low contrast",
    ),
    MessageCode.ACCESSIBILITY_IMAGE_MISSING_ALT_TEXT: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_IMAGE_MISSING_ALT_TEXT,
        summary="Image is missing alt text",
        template="Accessibility: image is missing alt text",
    ),
    MessageCode.ACCESSIBILITY_MARKDOWN_HEADING_LEVEL_SKIP: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_MARKDOWN_HEADING_LEVEL_SKIP,
        summary="Markdown heading levels skip",
        template="Accessibility: markdown heading levels skip",
    ),
    MessageCode.ACCESSIBILITY_HTML_HEADING_LEVEL_SKIP: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_HTML_HEADING_LEVEL_SKIP,
        summary="HTML heading levels skip",
        template="Accessibility: HTML heading levels skip",
    ),
    MessageCode.ACCESSIBILITY_EMPTY_LINK_TEXT: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_EMPTY_LINK_TEXT,
        summary="Link has no accessible text",
        template="Accessibility: link has no accessible text",
    ),
    MessageCode.ACCESSIBILITY_NON_DESCRIPTIVE_LINK_TEXT: MessageDefinition(
        code=MessageCode.ACCESSIBILITY_NON_DESCRIPTIVE_LINK_TEXT,
        summary="Link text is too generic",
        template="Accessibility: link text is too generic",
    ),
    MessageCode.VALIDATION_CODE_MISSING_VALIDATION_ERROR: MessageDefinition(
        code=MessageCode.VALIDATION_CODE_MISSING_VALIDATION_ERROR,
        summary="validation code should call validation_error()",
        template="validation code does not call validation_error(); consider calling validation_error(...) to provide user-facing error messages",
    ),
}


def format_message(code: str, **kwargs: object) -> str:
    if code not in MESSAGE_DEFINITIONS:
        raise ValueError(f"Unknown message code: {code!r}")
    return MESSAGE_DEFINITIONS[code].template.format(**kwargs)


def is_experimental_code(code: str) -> bool:
    if code not in MESSAGE_DEFINITIONS:
        raise ValueError(f"Unknown message code: {code!r}")
    return MESSAGE_DEFINITIONS[code].experimental
