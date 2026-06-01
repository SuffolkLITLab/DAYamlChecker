# Each doc, apply this to each block
import ast
import argparse
from dataclasses import dataclass, field, replace
from pathlib import Path
import re
import sys

from typing import Any, Optional
from dayamlchecker.accessibility import (
    AccessibilityLintOptions,
    find_accessibility_findings,
)
from dayamlchecker.messages import Finding, FindingClass, MessageId, draft, make_finding
from dayamlchecker.style import (
    ParsedInterviewDocument,
    StyleLintOptions,
    find_style_findings,
)
from mako.template import Template as MakoTemplate  # type: ignore[import-untyped]
from mako.exceptions import (  # type: ignore[import-untyped]
    SyntaxException,
    CompileException,
)
import esprima  # type: ignore[import-untyped]
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError
from dayamlchecker.check_questions_urls import (
    infer_package_dirs,
    infer_root as infer_url_check_root,
    parse_ignore_urls,
    print_url_check_report,
    run_url_check,
)

# TODO(brycew):
# * DA is fine with mixed case it looks like (i.e. Subquestion, vs subquestion)
# * what is "order"
# * can template and terms show up in same place?
# * can features and question show up in same place?
# * is "gathered" a valid attr?
# * handle "response"
# * labels above fields?
# * if "# use jinja" at top, process whole file with Jinja:
#   https://docassemble.org/docs/interviews.html#jinja2


__all__ = ["find_errors_from_string", "find_errors", "_collect_yaml_files"]

DEFAULT_LINT_MODE = "default"
ACCESSIBILITY_LINT_MODE = "accessibility"


@dataclass(frozen=True)
class RuntimeOptions:
    accessibility_error_on_widgets: frozenset[str] = field(default_factory=frozenset)
    style_enabled: bool = False
    style_include_llm: bool = False
    style_openai_base_url: str | None = None
    style_openai_api_key: str | None = None
    style_openai_model: str | None = None

    def accessibility_options(self) -> AccessibilityLintOptions:
        return AccessibilityLintOptions(
            error_on_widgets=self.accessibility_error_on_widgets
        )

    def style_options(self) -> StyleLintOptions:
        return StyleLintOptions(
            enabled=self.style_enabled or self.style_include_llm,
            include_llm=self.style_include_llm,
            openai_base_url=self.style_openai_base_url,
            openai_api_key=self.style_openai_api_key,
            openai_model=self.style_openai_model,
        )


# Global identifiers for _extract_conditional_fields_from_doc below. Should cover all show/hide style modifiers
_IDENTIFIER_RE = re.compile(r"[A-Za-z_]\w*")
_SIMPLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_]\w*$")
_JS_VAL_RE = re.compile(
    r"""val\s*\(\s*["']([^"']+)["']\s*\)"""
)  # matches val("fieldName") or val('fieldName') and captures fieldName
_SHOW_STYLE_MODIFIERS = {
    "show if",
    "enable if",
    "js show if",
    "js enable if",
}
_HIDE_STYLE_MODIFIERS = {
    "hide if",
    "disable if",
    "js hide if",
    "js disable if",
}
_CONDITIONAL_MODIFIERS = _SHOW_STYLE_MODIFIERS | _HIDE_STYLE_MODIFIERS

# Ensure that if there's a space in the str, it's between quotes.
space_in_str = re.compile("^[^ ]*['\"].* .*['\"][^ ]*$")


class YAMLStr:
    """Should be a direct YAML string, not a list or dict"""

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [draft(MessageId.YAML_STRING_REQUIRED, value_repr=repr(x))]


class MakoText:
    """A string that will be run through a Mako template from DA. Needs to have valid Mako template"""

    def __init__(self, x):
        self.errors = []
        try:
            self.template = MakoTemplate(
                x, strict_undefined=True, input_encoding="utf-8"
            )
        except SyntaxException as ex:
            self.errors = [
                draft(
                    MessageId.MAKO_SYNTAX_ERROR,
                    line_number=ex.lineno or 1,
                    error=str(ex),
                )
            ]
        except CompileException as ex:
            self.errors = [
                draft(
                    MessageId.MAKO_COMPILE_ERROR,
                    line_number=ex.lineno or 1,
                    error=str(ex),
                )
            ]


class MakoMarkdownText(MakoText):
    """A string that will be run through a Mako template from DA, then through a markdown formatter. Needs to have valid Mako template"""

    def __init__(self, x):
        super().__init__(x)


class PythonText:
    """A full multiline python script. Should have valid python syntax. i.e. a code block

    This validator parses the Python using the stdlib ast module and reports
    SyntaxError with the line number from the parsed code so the caller can
    translate it into the YAML file line number.
    """

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [
                draft(MessageId.PYTHON_CODE_TYPE, value_type=type(x).__name__)
            ]
            return
        try:
            ast.parse(x)
        except SyntaxError as ex:
            # ex.lineno gives line number within the code block
            lineno = ex.lineno or 1
            msg = ex.msg or str(ex)
            self.errors = [
                draft(MessageId.PYTHON_SYNTAX_ERROR, line_number=lineno, error=msg)
            ]


class ValidationCode(PythonText):
    """Validator for question-level `validation code`.

    In addition to Python syntax checking (inherited from PythonText), this
    emits a *warning* if the code does not call `validation_error(...)`,
    because validation code should normally call that function to explain
    validation failures to the user.
    """

    def __init__(self, x):
        super().__init__(x)
        # If there are already syntax errors, skip the usage check
        if self.errors:
            return
        try:
            tree = ast.parse(x)
        except SyntaxError:
            return
        # Walk AST and search for a call to validation_error(...)
        calls_validation_error = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "validation_error":
                    calls_validation_error = True
                    break
        if not calls_validation_error:
            # Suppress warning for transformation-only code blocks.
            # This includes assignments (even behind conditionals) and common
            # mutation helpers like define(...), which are intentionally used to
            # normalize output in many interviews.
            has_assignment = any(
                isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
                for n in ast.walk(tree)
            )
            has_define_call = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "define"
                for n in ast.walk(tree)
            )
            has_expr_call = any(
                isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                for n in ast.walk(tree)
            )
            has_raise_or_assert = any(
                isinstance(n, (ast.Raise, ast.Assert)) for n in ast.walk(tree)
            )
            if (
                has_assignment or has_define_call or has_expr_call
            ) and not has_raise_or_assert:
                return

            # Otherwise, emit a warning suggesting use of validation_error().
            # Use line number 1 because we don't have a more specific mapping here
            self.errors.append(
                draft(MessageId.VALIDATION_CODE_MISSING_VALIDATION_ERROR)
            )


class PythonBool:
    """Some text that needs to explicitly be a python bool, i.e. True, False, bool(1), but not 1"""

    def __init__(self, x):
        self.errors = []
        if isinstance(x, bool):
            return
        # number like 10 or 0 - not valid, even though Python treats them as truthy/falsy
        if isinstance(x, (int, float)):
            self.errors = [draft(MessageId.PYTHON_BOOL_NUMBER, value=x)]
            return
        # must be a string at this point
        if not isinstance(x, str):
            self.errors = [
                draft(MessageId.PYTHON_BOOL_TYPE, value_type=type(x).__name__)
            ]
            return
        # try parsing it as a Python expression - covers things like "user_age > 18"
        try:
            ast.parse(x)
        except SyntaxError as ex:
            msg = ex.msg or str(ex)
            self.errors = [draft(MessageId.PYTHON_BOOL_SYNTAX, value=x, error=msg)]


class JavascriptText:
    """Stuff that is considered Javascript, i.e. js show if"""

    def __init__(self, x):
        self.errors = []
        pass


class JSShowIf:
    """Validator for js show if/hide if/enable if/disable if field modifiers, checking:
    1) Valid JavaScript syntax (accounting for Mako expressions)
    2) Presence of at least one val() call
    3) That val() calls use quoted string literals for variable names
    """

    def __init__(self, x, modifier_key="js show if", screen_variables=None):
        self.errors = []
        self.screen_variables = screen_variables or set()
        if not isinstance(x, str):
            self.errors = [
                draft(
                    MessageId.JS_MODIFIER_TYPE,
                    modifier_key=modifier_key,
                    value_type=type(x).__name__,
                )
            ]
            return

        # Now check JavaScript syntax by removing Mako expressions first
        js_to_check = x
        mako_pattern = re.compile(r"\$\{[^}]*\}", re.DOTALL)
        js_to_check = mako_pattern.sub("true", js_to_check)

        try:
            parsed = esprima.parseScript(js_to_check, tolerant=False, loc=True).toDict()
        except esprima.Error as ex:
            self.errors.append(
                draft(
                    MessageId.JS_INVALID_SYNTAX,
                    line_number=getattr(ex, "lineNumber", 1) or 1,
                    modifier_key=modifier_key,
                    error=str(ex),
                )
            )
            return

        val_calls = []
        stack = [parsed]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("type") == "CallExpression":
                    callee = node.get("callee")
                    if (
                        isinstance(callee, dict)
                        and callee.get("type") == "Identifier"
                        and callee.get("name") == "val"
                    ):
                        val_calls.append(node)
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)

        if not val_calls:
            self.errors.append(
                draft(MessageId.JS_MISSING_VAL_CALL, modifier_key=modifier_key)
            )

        for call in val_calls:
            args = call.get("arguments") or []
            valid_arg = (
                len(args) == 1
                and isinstance(args[0], dict)
                and args[0].get("type") == "Literal"
                and isinstance(args[0].get("value"), str)
            )
            if valid_arg:
                var_name = args[0].get("value")
                if self.screen_variables and not self._references_screen_variable(
                    var_name
                ):
                    self.errors.append(
                        draft(
                            MessageId.JS_UNKNOWN_SCREEN_FIELD,
                            line_number=(
                                call.get("loc", {}).get("start", {}).get("line", 1) or 1
                            ),
                            modifier_key=modifier_key,
                            var_name=var_name,
                        )
                    )
                continue
            bad_arg = "<missing>"
            if args:
                first_arg = args[0]
                bad_arg = (
                    first_arg.get("raw")
                    or first_arg.get("name")
                    or first_arg.get("type", "<unknown>")
                )
            self.errors.append(
                draft(
                    MessageId.JS_VAL_ARG_NOT_QUOTED,
                    line_number=(
                        call.get("loc", {}).get("start", {}).get("line", 1) or 1
                    ),
                    bad_arg=bad_arg,
                )
            )

    def _references_screen_variable(self, var_expr):
        if not isinstance(var_expr, str):
            return False
        for candidate in self._variable_candidates(var_expr):
            if candidate in self.screen_variables:
                return True
        return False

    def _variable_candidates(self, var_expr):
        expr = var_expr.strip()
        candidates = {expr}
        if "." in expr:
            parts = expr.split(".")
            for i in range(len(parts), 0, -1):
                candidates.add(".".join(parts[:i]))
        expanded = set()
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            expanded.add(candidate)
            # Accept both full indexed paths and their base paths, e.g.:
            # children[i].parents["Other"] -> children[i].parents
            while candidate.endswith("]") and "[" in candidate:
                candidate = candidate[: candidate.rfind("[")].strip()
                if candidate:
                    expanded.add(candidate)
        return expanded


class ShowIf:
    """Validator for show if field modifier (non-js variants)
    Checks that if show if uses variable/code pattern, the referenced variable
    is defined on the same screen.
    """

    def __init__(self, x, context=None):
        self.errors = []
        self.context = context or {}

        if isinstance(x, str):
            # Shorthand form: show if: variable_name
            # This is only valid if variable_name refers to a yes/no field on the same screen
            if ":" not in x and " " not in x:  # Simple variable name
                # We can't validate this here without screen context
                # This will be validated at a higher level with fields context
                pass
            elif x.startswith("variable:") or x.startswith("code:"):
                # Malformed - these should be YAML dict format
                self.errors.append(draft(MessageId.SHOW_IF_MALFORMED, value=x))
        elif isinstance(x, dict):
            # YAML dict form
            if "variable" in x:
                # First method: show if: { variable: field_name, is: value }
                # Can only reference fields on the same screen - we'll validate in context
                pass
            elif "code" in x:
                # Third method: show if: { code: python_code }
                # Validate Python syntax for the provided code block
                code_block = x.get("code")
                if not isinstance(code_block, str):
                    self.errors.append(draft(MessageId.SHOW_IF_CODE_TYPE))
                else:
                    try:
                        ast.parse(code_block)
                    except SyntaxError as ex:
                        lineno = ex.lineno or 1
                        msg = ex.msg or str(ex)
                        self.errors.append(
                            draft(
                                MessageId.SHOW_IF_CODE_SYNTAX,
                                line_number=lineno,
                                error=msg,
                            )
                        )
            else:
                self.errors.append(draft(MessageId.SHOW_IF_DICT_KEYS))


class DAPythonVar:
    """Things that need to be defined as a docassemble var, i.e. abc or x.y['a']"""

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [draft(MessageId.PYTHON_VAR_TYPE, value_repr=repr(x))]
        elif " " in x and not space_in_str.search(x):
            self.errors = [draft(MessageId.PYTHON_VAR_WHITESPACE, value=x)]


class DAType:
    """Needs to be able to be a python defined types that's found at runtime in an interview, i.e. DAObject, Individual"""

    def __init__(self, x):
        self.errors = []
        pass


class ObjectsAttrType:
    def __init__(self, x):
        # The full typing desc of the var: TODO: how to use this?
        self.errors = []
        if not (isinstance(x, list) or isinstance(x, dict)):
            self.errors = [draft(MessageId.OBJECTS_BLOCK_TYPE, value_repr=repr(x))]
        # for entry in x:
        #   ...
        # if not isinstance(x, Union[list[dict[DAPythonVar, DAType]], dict[DAPythonVar, DAType]]):
        #  self.errors = [(f"Not objectAttrType isinstance! {x}", 1)]


class DAFields:
    modifier_keys = {
        "code",
        "default",
        "default value",
        "hint",
        "help",
        "label",
        "datatype",
        "choices",
        "validation code",
        "show if",
        "hide if",
        "js show if",
        "js hide if",
        "enable if",
        "disable if",
        "js enable if",
        "js disable if",
        "__line__",
    }

    mako_keys = {"default", "hint", "label", "note"}

    js_modifier_keys = ("js show if", "js hide if", "js enable if", "js disable if")
    py_modifier_keys = ("show if", "hide if", "enable if", "disable if")

    def __init__(self, x):
        self.errors = []
        self.has_dynamic_fields_code = False
        if isinstance(x, dict):
            if "code" not in x:
                self.errors = [draft(MessageId.FIELDS_DICT_KEYS, value_repr=repr(x))]
                return
            if not isinstance(x.get("code"), str):
                self.errors = [
                    draft(
                        MessageId.FIELDS_CODE_TYPE,
                        value_type=type(x.get("code")).__name__,
                    )
                ]
            return
        if not isinstance(x, list):
            self.errors = [draft(MessageId.FIELDS_TYPE, value_repr=repr(x))]
            return
        self._validate_field_modifiers(x)

    def _line_for(self, field_item, code_line=1):
        field_line = 1
        if isinstance(field_item, dict):
            field_line = field_item.get("__line__", 1)
        return field_line + max(code_line - 1, 0)

    def _extract_field_name(self, field_item):
        if not isinstance(field_item, dict):
            return None
        for key, value in field_item.items():
            if key in self.modifier_keys:
                continue
            if isinstance(value, str):
                return value
        return None

    def _validate_python_modifier(
        self, modifier_key, modifier_value, field_item, screen_variables
    ):
        def references_screen_variable(var_expr):
            if not isinstance(var_expr, str):
                return False
            candidates = self._variable_candidates(var_expr)
            if any(candidate in screen_variables for candidate in candidates):
                return True
            # In generic-object screens, x.<attr> often aliases another object path
            # like children[i].<attr>. Allow suffix match only when one side is x.<...>.
            for candidate in candidates:
                if candidate.startswith("x.") and any(
                    screen_var.endswith("." + candidate.split(".", 1)[1])
                    for screen_var in screen_variables
                ):
                    return True
            for screen_var in screen_variables:
                if screen_var.startswith("x.") and any(
                    candidate.endswith("." + screen_var.split(".", 1)[1])
                    for candidate in candidates
                ):
                    return True
            return False

        if isinstance(modifier_value, dict):
            if "variable" in modifier_value and "code" not in modifier_value:
                ref_var = modifier_value.get("variable")
                if not isinstance(ref_var, str):
                    self.errors.append(
                        draft(
                            MessageId.FIELD_MODIFIER_VARIABLE_TYPE,
                            line_number=self._line_for(field_item),
                            modifier_key=modifier_key,
                            value_type=type(ref_var).__name__,
                        )
                    )
                elif not references_screen_variable(ref_var):
                    self.errors.append(
                        draft(
                            MessageId.FIELD_MODIFIER_UNKNOWN_VARIABLE_DICT,
                            line_number=self._line_for(field_item),
                            modifier_key=modifier_key,
                            variable=ref_var,
                        )
                    )
            elif "code" in modifier_value:
                code_text = modifier_value.get("code")
                validator = PythonText(code_text)
                for err in validator.errors:
                    self.errors.append(
                        draft(
                            MessageId.FIELD_MODIFIER_CODE_ERROR,
                            line_number=self._line_for(
                                field_item, err.line_number or 1
                            ),
                            modifier_key=modifier_key,
                            detail=err.message.lower(),
                        )
                    )
                if (
                    modifier_key == "show if"
                    and isinstance(code_text, str)
                    and not validator.errors
                ):
                    same_screen_refs = self._find_screen_variable_references_in_code(
                        code_text, screen_variables
                    )
                    if same_screen_refs:
                        refs = ", ".join(sorted(same_screen_refs))
                        self.errors.append(
                            draft(
                                MessageId.FIELD_MODIFIER_SAME_SCREEN_CODE,
                                line_number=self._line_for(field_item),
                                modifier_key=modifier_key,
                                variables=refs,
                            )
                        )
            else:
                self.errors.append(
                    draft(
                        MessageId.FIELD_MODIFIER_DICT_KEYS,
                        line_number=self._line_for(field_item),
                        modifier_key=modifier_key,
                    )
                )
        elif isinstance(modifier_value, str) and ":" not in modifier_value:
            if not references_screen_variable(modifier_value):
                self.errors.append(
                    draft(
                        MessageId.FIELD_MODIFIER_UNKNOWN_VARIABLE_STRING,
                        line_number=self._line_for(field_item),
                        modifier_key=modifier_key,
                        variable=modifier_value,
                    )
                )

    def _find_screen_variable_references_in_code(self, code_text, screen_variables):
        try:
            tree = ast.parse(code_text)
        except SyntaxError:
            return set()

        name_refs = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        matches = set()
        for screen_var in screen_variables:
            if _SIMPLE_IDENTIFIER_RE.match(screen_var) and screen_var in name_refs:
                matches.add(screen_var)
                continue
            # For dotted/indexed vars, require explicit textual reference.
            if _find_variable_reference_lines(code_text, screen_var):
                matches.add(screen_var)
        return matches

    def _validate_field_modifiers(self, fields_list):
        self.has_dynamic_fields_code = any(  # looking for any example in the field list. Note that there can be `code` and traditional non-code mixed in the same field list
            isinstance(field_item, dict)
            and "code" in field_item
            and len(set(field_item.keys()) - {"code", "__line__"})
            == 0  # "code" is the only key other than __line__, so this is a dynamic fields block
            for field_item in fields_list
        )
        screen_variables = set()
        for field_item in fields_list:
            field_var_name = self._extract_field_name(field_item)
            if field_var_name:
                screen_variables.add(field_var_name)

        for field_item in fields_list:
            if not isinstance(field_item, dict):
                continue

            for field_key in field_item:
                if isinstance(field_key, str) and field_key != "__line__":
                    if (
                        field_key not in self.modifier_keys
                        and field_key.lower() in self.modifier_keys
                    ):
                        self.errors.append(
                            draft(
                                MessageId.FIELD_MODIFIER_CASE,
                                line_number=self._line_for(field_item),
                                field_key=field_key,
                                suggested_key=field_key.lower(),
                            )
                        )
                    if field_key in self.mako_keys:
                        the_mako = MakoText(str(field_item[field_key]))
                        for err in the_mako.errors:
                            field_message_id = (
                                MessageId.FIELD_VALUE_MAKO_SYNTAX_ERROR
                                if err.message_id == MessageId.MAKO_SYNTAX_ERROR
                                else MessageId.FIELD_VALUE_MAKO_COMPILE_ERROR
                            )
                            self.errors.append(
                                draft(
                                    field_message_id,
                                    line_number=self._line_for(
                                        field_item, err.line_number or 1
                                    ),
                                    field_key=field_key,
                                    **dict(err.context),
                                )
                            )

            for js_key in self.js_modifier_keys:
                if js_key in field_item:
                    validator = JSShowIf(
                        field_item[js_key],
                        modifier_key=js_key,
                        screen_variables=screen_variables,
                    )
                    for err in validator.errors:
                        if (
                            self.has_dynamic_fields_code
                            and err.message_id == MessageId.JS_UNKNOWN_SCREEN_FIELD
                        ):
                            self.errors.append(
                                draft(
                                    MessageId.JS_UNKNOWN_SCREEN_FIELD_PARTIAL,
                                    line_number=self._line_for(
                                        field_item, err.line_number or 1
                                    ),
                                    **dict(err.context),
                                )
                            )
                            continue
                        self.errors.append(
                            draft(
                                err.message_id,
                                line_number=self._line_for(
                                    field_item, err.line_number or 1
                                ),
                                **dict(err.context),
                            )
                        )

            for py_key in self.py_modifier_keys:
                if py_key in field_item:
                    self._validate_python_modifier(
                        py_key, field_item[py_key], field_item, screen_variables
                    )

    def _variable_candidates(self, var_expr):
        expr = var_expr.strip()
        candidates = {expr}
        if "." in expr:
            parts = expr.split(".")
            for i in range(len(parts), 0, -1):
                candidates.add(".".join(parts[:i]))
        expanded = set()
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            expanded.add(candidate)
            # Accept both full indexed paths and their base paths, e.g.:
            # children[i].parents["Other"] -> children[i].parents
            while candidate.endswith("]") and "[" in candidate:
                candidate = candidate[: candidate.rfind("[")].strip()
                if candidate:
                    expanded.add(candidate)
        return expanded


# type notes what the value for that dictionary key is,

# More notes:
# mandatory can only be used on:
# question, code, objects, attachment, data, data from code

# TODO(brycew): composable validators! One validator that works with just lists of single entry dicts with a str as the key, and a DAPythonVar as the value, and another that expects a code block, then an OR validator that takes both and works with either.
# Works with smaller blocks, prevents a lot of duplicate nested code
big_dict: dict[str, dict[str, Any]] = {
    "question": {
        "type": MakoMarkdownText,
    },
    "subquestion": {
        "type": MakoMarkdownText,
    },
    "mandatory": {"type": PythonBool},
    "code": {"type": PythonText},
    "objects": {
        "type": ObjectsAttrType,
    },
    "id": {
        "type": YAMLStr,
    },
    "ga id": {
        "type": YAMLStr,
    },
    "segment id": {
        "type": YAMLStr,
    },
    "features": {},
    "terms": {},
    "auto terms": {},
    "help": {},
    "fields": {"type": DAFields},
    "buttons": {},
    "field": {"type": DAPythonVar},
    "template": {},
    "content": {},
    "reconsider": {},
    "depends on": {},
    "need": {},
    "attachment": {},
    "table": {},
    "rows": {},
    "allow reordering": {},
    "columns": {},
    "delete buttons": {},
    "validation code": {
        "type": ValidationCode,
    },
    "translations": {},
    "include": {},
    "default screen parts": {},
    "metadata": {},
    "modules": {},
    "imports": {},
    "sections": {},
    "language": {},
    "interview help": {},
    "def": {
        "type": DAPythonVar,
    },
    "mako": {
        "type": MakoText,
    },
    "usedefs": {},
    "default role": {},  # use with code
    "default language": {},
    "default validation messages": {},
    "machine learning storage": {},
    "scan for variables": {},
    "if": {},
    "sets": {},
    "initial": {"type": PythonBool},
    "event": {},
    "comment": {},
    "generic object": {"type": DAPythonVar},
    "variable name": {},
    "data from code": {},
    "back button label": {},
    "continue button label": {
        "type": YAMLStr,
    },
    "decoration": {},
    "yesno": {"type": DAPythonVar},
    "noyes": {"type": DAPythonVar},
    "yesnomaybe": {"type": DAPythonVar},
    "noyesmaybe": {"type": DAPythonVar},
    "reset": {},
    "on change": {},
    "image sets": {},
    "images": {},
    "interview help": {},
    "continue button field": {
        "type": DAPythonVar,
    },
    "disable others": {},
    "order": {},
}

# need a list of blocks; certain attributes imply certain blocks, and block out other things,
# like question and code

# Not all blocks are necessary: comment can be by itself, and attachment can be with question, or alone

# ordered by priority
# TODO: brycew: consider making required_attrs
types_of_blocks: dict[str, dict[str, Any]] = {
    "include": {
        "exclusive": True,
        "allowed_attrs": ["include"],
    },
    "features": {  # don't get an error, but code and question attributes aren't recognized
        "exclusive": True,
        "allowed_attrs": [
            "features",
        ],
    },
    "objects": {
        "exclusive": True,
        "allowed_attrs": [
            "objects",
        ],
    },
    "objects from file": {
        "exclusive": True,
        "allowed_attrs": [
            "objects from file",
            "use objects",
        ],
    },
    "sections": {
        "exclusive": True,
        "allowed_attrs": [
            "sections",
        ],
    },
    "imports": {
        "exclusive": True,
        "allowed_attrs": [
            "imports",
        ],
    },
    "order": {
        "exclusive": True,
        "allowed_attrs": ["order"],
    },
    "attachment": {
        "exclusive": True,
        "partners": ["question"],
    },
    "attachments": {
        "exclusive": True,
        "partners": ["question"],
    },
    "template": {
        "exclusive": True,
        "allowed_attrs": [
            "template",
            "content",
            "language",
            "subject",
            "generic object",
            "content file",
            "reconsider",
        ],
        "partners": ["terms"],
    },
    "table": {
        "exclusive": True,
        "allowed_attrs": {
            "sort key",
            "filter",
        },
    },  # maybe?
    "translations": {},
    "modules": {},
    "mako": {},  # includes def
    "auto terms": {"exclusive": True, "partners": ["question"]},
    "terms": {"exclusive": True, "partners": ["question", "template"]},
    "variable name": {"exclusive:": True, "allowed_attrs": {"gathered", "data"}},
    "default language": {},
    "default validation messages": {},
    "reset": {},
    "on change": {},
    "images": {},
    "image sets": {},
    "default screen parts": {
        "allowed_attrs": [
            "default screen parts",
        ],
    },
    "metadata": {},
    "question": {
        "exclusive": True,
        "partners": ["auto terms", "terms", "attachment", "attachments"],
    },
    "response": {
        "exclusive": True,
        "allowed_attrs": [
            "event",
            "mandatory",
        ],
    },
    "code": {},
    "comment": {"exclusive": False},
    "interview help": {
        "exclusive": True,
    },
    "machine learning storage": {},
}

#######
# These things are from DA's source code. Since this should be lightweight,
# I don't want to directly include things from DA. We'll see if that works.
#
# Last updated: 1.7.7, 484736005270dd6107
#######

# From parse.py:89-91
document_match = re.compile(r"^--- *$", flags=re.MULTILINE)
remove_trailing_dots = re.compile(r"[\n\r]+\.\.\.$")
fix_tabs = re.compile(r"\t")

# All of the known dictionary keys: from docassemble/base/parse.py:2186, in Question.__init__
all_dict_keys = (
    "features",
    "scan for variables",
    "only sets",
    "question",
    "code",
    "event",
    "translations",
    "default language",
    "on change",
    "sections",
    "progressive",
    "auto open",
    "section",
    "machine learning storage",
    "language",
    "prevent going back",
    "back button",
    "usedefs",
    "continue button label",
    "continue button color",
    "resume button label",
    "resume button color",
    "back button label",
    "corner back button label",
    "skip undefined",
    "list collect",
    "mandatory",
    "attachment options",
    "script",
    "css",
    "initial",
    "default role",
    "command",
    "objects from file",
    "use objects",
    "data",
    "variable name",
    "data from code",
    "objects",
    "id",
    "ga id",
    "segment id",
    "segment",
    "supersedes",
    "order",
    "image sets",
    "images",
    "def",
    "mako",
    "interview help",
    "default screen parts",
    "default validation messages",
    "generic object",
    "generic list object",
    "comment",
    "metadata",
    "modules",
    "reset",
    "imports",
    "terms",
    "auto terms",
    "role",
    "include",
    "action buttons",
    "if",
    "validation code",
    "require",
    "orelse",
    "attachment",
    "attachments",
    "attachment code",
    "attachments code",
    "allow emailing",
    "allow downloading",
    "email subject",
    "email body",
    "email template",
    "email address default",
    "progress",
    "zip filename",
    "action",
    "backgroundresponse",
    "response",
    "binaryresponse",
    "all_variables",
    "response filename",
    "content type",
    "redirect url",
    "null response",
    "sleep",
    "include_internal",
    "css class",
    "table css class",
    "response code",
    "subquestion",
    "reload",
    "help",
    "audio",
    "video",
    "decoration",
    "signature",
    "under",
    "pre",
    "post",
    "right",
    "check in",
    "yesno",
    "noyes",
    "yesnomaybe",
    "noyesmaybe",
    "sets",
    "event",
    "choices",
    "buttons",
    "dropdown",
    "combobox",
    "field",
    "shuffle",
    "review",
    "need",
    "depends on",
    "target",
    "table",
    "rows",
    "columns",
    "require gathered",
    "allow reordering",
    "edit",
    "delete buttons",
    "confirm",
    "read only",
    "edit header",
    "confirm",
    "show if empty",
    "template",
    "content file",
    "content",
    "subject",
    "reconsider",
    "undefine",
    "continue button field",
    "fields",
    "indent",
    "url",
    "default",
    "datatype",
    "extras",
    "allowed to set",
    "show incomplete",
    "not available label",
    "required",
    "always include editable files",
    "question metadata",
    "include attachment notice",
    "include download tab",
    "describe file types",
    "manual attachment list",
    "breadcrumb",
    "tabular",
    "hide continue button",
    "disable continue button",
    "pen color",
    "gathered",
    "show if",
    "hide if",
    "js show if",
    "js hide if",
    "enable if",
    "disable if",
    "js enable if",
    "js disable if",
    "disable others",
) + (  # things that are only present in tables, features, etc., i.e. non question blocks.
    "filter",
    "sort key",
    "sort reverse",
)


def _lowercase_key_map(mapping: dict[Any, Any]) -> dict[str, str]:
    return {
        key.lower(): key
        for key in mapping.keys()
        if isinstance(key, str) and key != "__line__"
    }


def _get_case_insensitive(
    mapping: dict[Any, Any], key: str, default: Any = None
) -> Any:
    original_key = _lowercase_key_map(mapping).get(key.lower())
    if original_key is None:
        return default
    return mapping.get(original_key, default)


YAMLError = Finding


def _yaml_error_message_id(error_text: str) -> str:
    lowered = error_text.lower()
    if "duplicate key" in lowered or "found duplicate key" in lowered:
        return MessageId.YAML_DUPLICATE_KEY
    return MessageId.YAML_PARSE_ERROR


def _yaml_error_line_number(
    error: MarkedYAMLError, full_content: str, default_line_number: int
) -> int:
    lines = full_content.splitlines()
    for mark in (error.problem_mark, error.context_mark):
        if mark is None:
            continue
        if 0 <= mark.line < len(lines) and lines[mark.line].strip():
            return mark.line + 1
    for mark in (error.problem_mark, error.context_mark):
        if mark is not None:
            return mark.line + 1
    return default_line_number


def _make_yaml_parser() -> YAML:
    yaml = YAML()
    yaml.allow_duplicate_keys = False
    return yaml


def _with_line_metadata(value: Any) -> Any:
    if isinstance(value, CommentedMap):
        converted: dict[Any, Any] = {
            key: _with_line_metadata(item) for key, item in value.items()
        }
        converted["__line__"] = value.lc.line + 1
        return converted
    if isinstance(value, CommentedSeq):
        return [_with_line_metadata(item) for item in value]
    return value


def _normalize_expr(expr: str) -> str:
    normalized = re.sub(r"\s+", "", expr or "")
    return normalized.replace('"', "'")


def _contains_interview_order_marker(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return "interview_order" in lowered or "interview order" in lowered
    return False


def _is_interview_order_style_block(doc: dict[str, Any]) -> bool:
    mandatory = _get_case_insensitive(doc, "mandatory")
    mandatory_true = mandatory is True or (
        isinstance(mandatory, str) and mandatory.strip().lower() == "true"
    )
    if mandatory_true:
        return True
    if _contains_interview_order_marker(_get_case_insensitive(doc, "id")):
        return True
    if _contains_interview_order_marker(_get_case_insensitive(doc, "comment")):
        return True
    return False


def _extract_field_var_name(field_item: Any) -> Optional[str]:
    if not isinstance(field_item, dict):
        return None
    modifier_keys = DAFields.modifier_keys
    for key, value in field_item.items():
        if key in modifier_keys:
            continue
        if isinstance(value, str):
            return value
    return None


def _extract_names_from_python_expr(expr: str) -> set[str]:
    names: set[str] = set()
    try:
        tree = ast.parse(expr)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


def _extract_controller_vars_for_field_modifier(modifier_value: Any) -> set[str]:
    if isinstance(modifier_value, str):
        return set(_IDENTIFIER_RE.findall(modifier_value))
    if isinstance(modifier_value, dict):
        vars_found: set[str] = set()
        ref_var = modifier_value.get("variable")
        if isinstance(ref_var, str):
            vars_found.update(_IDENTIFIER_RE.findall(ref_var))
        code = modifier_value.get("code")
        if isinstance(code, str):
            vars_found.update(_extract_names_from_python_expr(code))
        return vars_found
    return set()


def _extract_vars_from_js_condition(cond: str) -> set[str]:
    if not isinstance(cond, str):
        return set()
    return {m.group(1) for m in _JS_VAL_RE.finditer(cond)}


def _invert_simple_comparison(cond: str) -> Optional[str]:
    m = re.match(r"^\s*(.+?)\s*(==|!=)\s*(.+?)\s*$", cond or "")
    if not m:
        return None
    left, op, right = m.groups()
    inv_op = "!=" if op == "==" else "=="
    return f"{left.strip()} {inv_op} {right.strip()}"


def _guard_candidates_for_modifier(modifier_key: str, modifier_value: Any) -> list[str]:
    is_hide = modifier_key in _HIDE_STYLE_MODIFIERS
    is_js = modifier_key.startswith("js ")
    guards: list[str] = []

    if is_js and isinstance(modifier_value, str):
        vars_found = sorted(_extract_vars_from_js_condition(modifier_value))
        for var_name in vars_found:
            if is_hide:
                guards.append(f"not ({var_name})")
                guards.append(f"not {var_name}")
            else:
                guards.append(var_name)
        # Keep raw condition as a fallback for textual matching
        guards.append(modifier_value.strip())
        return [guard for guard in guards if guard]

    if isinstance(modifier_value, str):
        cond = modifier_value.strip()
        if not cond:
            return guards
        if is_hide:
            guards.append(f"not ({cond})")
            guards.append(f"not {cond}")
            inverted = _invert_simple_comparison(cond)
            if inverted:
                guards.append(inverted)
        else:
            guards.append(cond)
        return guards

    if not isinstance(modifier_value, dict):
        return guards

    ref_var = modifier_value.get("variable")
    has_is = "is" in modifier_value
    is_val = modifier_value.get("is")
    code = modifier_value.get("code")

    if isinstance(ref_var, str):
        if has_is:
            if is_hide:
                guards.append(f"{ref_var} != {repr(is_val)}")
                guards.append(f"not ({ref_var} == {repr(is_val)})")
            else:
                guards.append(f"{ref_var} == {repr(is_val)}")
        else:
            if is_hide:
                guards.append(f"not ({ref_var})")
                guards.append(f"not {ref_var}")
            else:
                guards.append(ref_var)
    elif isinstance(code, str):
        if is_hide:
            guards.append(f"not ({code.strip()})")
        else:
            guards.append(code.strip())

    return [guard for guard in guards if guard]


def _extract_conditional_fields_from_doc(
    doc: dict[str, Any], line_number: int
) -> list[dict[str, Any]]:
    fields = _get_case_insensitive(doc, "fields")
    if not isinstance(fields, list):
        return []

    conditional_fields: list[dict[str, Any]] = []
    for field_item in fields:
        field_var = _extract_field_var_name(field_item)
        if not field_var or not isinstance(field_item, dict):
            continue

        for modifier_key in _CONDITIONAL_MODIFIERS:
            if modifier_key not in field_item:
                continue
            modifier_value = field_item[modifier_key]
            guards = _guard_candidates_for_modifier(modifier_key, modifier_value)
            if not guards:
                continue
            conditional_fields.append(
                {
                    "field_var": field_var,
                    "guards": guards,
                    "line_number": line_number + field_item.get("__line__", 1),
                }
            )
    return conditional_fields


def _find_variable_reference_lines(code: str, variable_expr: str) -> list[int]:
    lines = code.splitlines()
    if _SIMPLE_IDENTIFIER_RE.match(variable_expr):
        pattern = re.compile(rf"\b{re.escape(variable_expr)}\b")
    else:
        # Avoid prefix false positives like matching "foo.bar" inside "foo.bar2".
        pattern = re.compile(rf"{re.escape(variable_expr)}(?!\w)")
    return [i + 1 for i, line in enumerate(lines) if pattern.search(line)]


def _statement_span(stmts: list[ast.stmt]) -> Optional[tuple[int, int]]:
    if not stmts:
        return None
    starts = [getattr(stmt, "lineno", None) for stmt in stmts]
    ends = [
        getattr(stmt, "end_lineno", getattr(stmt, "lineno", None)) for stmt in stmts
    ]
    valid_starts = [x for x in starts if isinstance(x, int)]
    valid_ends = [x for x in ends if isinstance(x, int)]
    if not valid_starts or not valid_ends:
        return None
    return (min(valid_starts), max(valid_ends))


def _extract_branch_guards_by_line(code: str) -> dict[int, list[str]]:
    guards_by_line: dict[int, list[str]] = {}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return guards_by_line

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        cond = ast.get_source_segment(code, node.test)
        if not cond:
            try:
                cond = ast.unparse(node.test)
            except Exception:
                cond = ""
        if not cond:
            continue

        # The condition line itself is a guard context for references inside
        # the test expression (e.g., if showifdef("x") and x: ...).
        if isinstance(getattr(node, "lineno", None), int):
            guards_by_line.setdefault(node.lineno, []).append(cond)

        body_span = _statement_span(node.body)
        if body_span:
            for line in range(body_span[0], body_span[1] + 1):
                guards_by_line.setdefault(line, []).append(cond)

        orelse_span = _statement_span(node.orelse)
        if orelse_span:
            negated = f"not ({cond})"
            for line in range(orelse_span[0], orelse_span[1] + 1):
                guards_by_line.setdefault(line, []).append(negated)

    return guards_by_line


def _has_showifdef_guard(active_guards: list[str], field_var: str) -> bool:
    quoted_var = re.escape(field_var)
    showifdef_pattern = re.compile(rf"showifdef\s*\(\s*['\"]{quoted_var}['\"]\s*\)")
    return any(showifdef_pattern.search(guard or "") for guard in active_guards)


def _has_matching_guard(active_guards: list[str], expected_guards: list[str]) -> bool:
    expected_norm = [_normalize_expr(guard) for guard in expected_guards if guard]
    if not expected_norm:
        return True
    for guard in active_guards:
        guard_norm = _normalize_expr(guard)
        if any(expected in guard_norm for expected in expected_norm):
            return True
    return False


def _find_unmatched_interview_order_references(
    doc: dict[str, Any], conditional_fields: list[dict[str, Any]]
) -> list[tuple[str, int]]:
    code = _get_case_insensitive(doc, "code")
    if not isinstance(code, str):
        return []
    if not _is_interview_order_style_block(doc):
        return []

    guards_by_line = _extract_branch_guards_by_line(code)
    unmatched: list[tuple[str, int]] = []
    seen_fields: set[str] = set()
    for conditional in conditional_fields:
        field_var = conditional["field_var"]
        if field_var in seen_fields:
            continue
        expected_guards = conditional["guards"]
        for ref_line in _find_variable_reference_lines(code, field_var):
            active_guards = guards_by_line.get(ref_line, [])
            if _has_showifdef_guard(active_guards, field_var):
                continue
            if not _has_matching_guard(active_guards, expected_guards):
                seen_fields.add(field_var)
                unmatched.append((field_var, ref_line))
                break
    return unmatched


def _max_screen_visibility_nesting_depth(doc: dict[str, Any]) -> int:
    fields = _get_case_insensitive(doc, "fields")
    if not isinstance(fields, list):
        return 0

    screen_vars = {
        field_var
        for field_var in (_extract_field_var_name(item) for item in fields)
        if field_var
    }
    if not screen_vars:
        return 0

    adjacency: dict[str, set[str]] = {var: set() for var in screen_vars}
    for field_item in fields:
        if not isinstance(field_item, dict):
            continue
        target_var = _extract_field_var_name(field_item)
        if not target_var:
            continue
        for modifier_key in ("show if", "hide if"):
            if modifier_key not in field_item:
                continue
            controllers = _extract_controller_vars_for_field_modifier(
                field_item[modifier_key]
            )
            for controller in controllers:
                if controller in screen_vars:
                    adjacency.setdefault(controller, set()).add(target_var)

    visiting: set[str] = set()
    memo: dict[str, int] = {}

    def depth(var_name: str) -> int:
        if var_name in memo:
            return memo[var_name]
        if var_name in visiting:
            return 0
        visiting.add(var_name)
        max_child = 0
        for child in adjacency.get(var_name, set()):
            max_child = max(max_child, 1 + depth(child))
        visiting.remove(var_name)
        memo[var_name] = max_child
        return max_child

    return max((depth(var) for var in adjacency.keys()), default=0)


def find_errors_from_string(
    full_content: str,
    input_file: Optional[str] = None,
    lint_mode: str = DEFAULT_LINT_MODE,
    runtime_options: Optional[RuntimeOptions] = None,
) -> list[YAMLError]:
    """Return list of findings found in the given full_content string

    Args:
        full_content (str): Full YAML content as a string.
    Returns:
        list[YAMLError]: List of findings found in the content.
    """
    all_errors: list[YAMLError] = []
    runtime_options = runtime_options or RuntimeOptions()

    if not input_file:
        input_file = "<string input>"

    exclusive_keys = [
        key
        for key in types_of_blocks.keys()
        if types_of_blocks[key].get("exclusive", True)
    ]
    yaml_parser = _make_yaml_parser()
    prior_conditional_fields: list[dict[str, Any]] = []
    parsed_docs: list[ParsedInterviewDocument] = []
    has_yaml_parse_errors = False
    line_number = 1
    for source_code in document_match.split(full_content):
        lines_in_code = sum(l == "\n" for l in source_code)
        source_code = remove_trailing_dots.sub("", source_code)
        source_code = fix_tabs.sub("  ", source_code)
        try:
            doc = _with_line_metadata(yaml_parser.load(source_code))
        except Exception as errMess:
            error_line_number = line_number
            if isinstance(errMess, MarkedYAMLError):
                if errMess.context_mark is not None:
                    errMess.context_mark.line += line_number - 1
                if errMess.problem_mark is not None:
                    errMess.problem_mark.line += line_number - 1
                error_line_number = _yaml_error_line_number(
                    errMess, full_content, line_number
                )
            rendered_error = str(errMess)
            all_errors.append(
                make_finding(
                    _yaml_error_message_id(rendered_error),
                    line_number=error_line_number,
                    file_name=input_file,
                    error=rendered_error,
                )
            )
            has_yaml_parse_errors = True
            line_number += lines_in_code
            continue

        if doc is None:
            # Just YAML comments, that's fine
            line_number += lines_in_code
            continue
        if not isinstance(doc, dict):
            line_number += lines_in_code
            continue

        if lint_mode == ACCESSIBILITY_LINT_MODE:
            accessibility_findings = find_accessibility_findings(
                doc=doc,
                source_code=source_code,
                document_start_line=line_number,
                input_file=input_file,
                options=runtime_options.accessibility_options(),
            )
            all_errors.extend(accessibility_findings)

        doc_keys_lower = _lowercase_key_map(doc)
        non_meta_keys_lower = {
            key.lower()
            for key in doc.keys()
            if isinstance(key, str) and key != "__line__"
        }
        if non_meta_keys_lower == {"comment"}:
            # docassemble ignores comment-only blocks, but once another attribute
            # is present the block still needs a real question/directive type.
            pass
        else:
            any_types = [
                block
                for block in types_of_blocks.keys()
                if block in doc_keys_lower and block != "comment"
            ]
            if len(any_types) == 0:
                all_errors.append(
                    make_finding(
                        MessageId.NO_POSSIBLE_TYPES,
                        line_number=line_number,
                        file_name=input_file,
                    )
                )
        posb_types = [block for block in exclusive_keys if block in doc_keys_lower]
        if len(posb_types) > 1:
            if len(posb_types) == 2 and posb_types[1] in (
                types_of_blocks[posb_types[0]].get("partners") or []
            ):
                pass
            else:
                all_errors.append(
                    make_finding(
                        MessageId.TOO_MANY_TYPES,
                        line_number=line_number,
                        file_name=input_file,
                        block_types=", ".join(posb_types),
                    )
                )

        weird_keys = []
        for attr in doc.keys():
            if attr == "__line__":
                continue
            if not isinstance(attr, str):
                # Non-string keys (e.g., bools) are not expected in DA interview files
                weird_keys.append(str(attr))
            elif attr.lower() not in all_dict_keys:
                weird_keys.append(attr)
        if len(weird_keys) > 0:
            all_errors.append(
                make_finding(
                    MessageId.UNKNOWN_KEYS,
                    line_number=line_number,
                    file_name=input_file,
                    keys=", ".join(weird_keys),
                )
            )
        for key in doc.keys():
            if not isinstance(key, str):
                continue
            lower_key = key.lower()
            if lower_key in big_dict and "type" in big_dict[lower_key]:
                test = big_dict[lower_key]["type"](doc[key])
                for err in test.errors:
                    all_errors.append(
                        err.to_finding(
                            file_name=input_file,
                            line_number=(err.line_number or 1)
                            + doc["__line__"]
                            + line_number,
                        )
                    )

        unmatched_refs = _find_unmatched_interview_order_references(
            doc, prior_conditional_fields
        )
        for field_var, ref_line in unmatched_refs:
            all_errors.append(
                make_finding(
                    MessageId.INTERVIEW_ORDER_UNMATCHED_GUARD,
                    line_number=doc["__line__"] + line_number + ref_line,
                    file_name=input_file,
                    field_name=field_var,
                )
            )

        nesting_depth = _max_screen_visibility_nesting_depth(doc)
        if nesting_depth > 2:
            all_errors.append(
                make_finding(
                    MessageId.NESTED_VISIBILITY_LOGIC,
                    line_number=doc["__line__"] + line_number,
                    file_name=input_file,
                    nesting_depth=nesting_depth,
                )
            )

        prior_conditional_fields.extend(
            _extract_conditional_fields_from_doc(doc, line_number)
        )
        parsed_docs.append(
            ParsedInterviewDocument(
                doc=doc,
                source_code=source_code,
                document_start_line=line_number,
                index=len(parsed_docs),
            )
        )

        line_number += lines_in_code
    if not has_yaml_parse_errors:
        all_errors.extend(
            _find_interview_level_findings(parsed_docs, input_file=input_file)
        )
    style_options = runtime_options.style_options()
    if style_options.enabled and not has_yaml_parse_errors:
        all_errors.extend(
            find_style_findings(
                docs=parsed_docs,
                input_file=input_file,
                options=style_options,
            )
        )
    return all_errors


_COMMON_COURTFORMSONLINE_METADATA_FIELDS = (
    "title",
    "short title",
    "description",
    "can_I_use_this_form",
    "before_you_start",
    "LIST_topics",
    "jurisdiction",
)


def _find_interview_level_findings(
    parsed_docs: list[ParsedInterviewDocument], *, input_file: str
) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_check_missing_question_ids(parsed_docs, input_file=input_file))
    findings.extend(
        _check_multiple_mandatory_blocks(parsed_docs, input_file=input_file)
    )
    findings.extend(_check_metadata_fields(parsed_docs, input_file=input_file))
    return findings


def _check_missing_question_ids(
    parsed_docs: list[ParsedInterviewDocument], *, input_file: str
) -> list[Finding]:
    if not _looks_like_interview_file(parsed_docs):
        return []
    findings: list[Finding] = []
    for parsed_doc in parsed_docs:
        question = str(parsed_doc.doc.get("question") or "").strip()
        if not question or str(parsed_doc.doc.get("id") or "").strip():
            continue
        findings.append(
            make_finding(
                MessageId.MISSING_QUESTION_ID,
                file_name=input_file,
                line_number=parsed_doc.line_for_key("question"),
                snippet=_shorten(question),
            )
        )
    return findings


def _check_multiple_mandatory_blocks(
    parsed_docs: list[ParsedInterviewDocument], *, input_file: str
) -> list[Finding]:
    mandatory_docs = [
        parsed_doc
        for parsed_doc in parsed_docs
        if _is_truthy(parsed_doc.doc.get("mandatory"))
    ]
    if len(mandatory_docs) < 2:
        return []
    labels = []
    for parsed_doc in mandatory_docs[:4]:
        label = str(
            parsed_doc.doc.get("id") or parsed_doc.doc.get("question") or ""
        ).strip()
        labels.append(_shorten(label or parsed_doc.screen_id))
    return [
        make_finding(
            MessageId.MULTIPLE_MANDATORY_BLOCKS,
            file_name=input_file,
            line_number=mandatory_docs[1].line_for_key("mandatory"),
            labels=", ".join(labels),
        )
    ]


def _check_metadata_fields(
    parsed_docs: list[ParsedInterviewDocument], *, input_file: str
) -> list[Finding]:
    metadata_doc: Optional[ParsedInterviewDocument] = None
    metadata: dict[str, Any] = {}
    for parsed_doc in parsed_docs:
        block = parsed_doc.doc.get("metadata")
        if not isinstance(block, dict):
            continue
        if metadata_doc is None:
            metadata_doc = parsed_doc
        metadata.update(block)
    if metadata_doc is None:
        return []
    missing = [
        field
        for field in _COMMON_COURTFORMSONLINE_METADATA_FIELDS
        if not metadata.get(field)
    ]
    if not missing:
        return []
    return [
        make_finding(
            MessageId.MISSING_METADATA_FIELDS,
            file_name=input_file,
            line_number=metadata_doc.line_for_key("metadata"),
            fields=", ".join(missing),
        )
    ]


def _looks_like_interview_file(parsed_docs: list[ParsedInterviewDocument]) -> bool:
    if len(parsed_docs) > 1:
        return True
    for parsed_doc in parsed_docs:
        if parsed_doc.doc.get("metadata") is not None:
            return True
        if parsed_doc.doc.get("include") is not None:
            return True
        if parsed_doc.doc.get("mandatory") is not None:
            return True
    return False


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "on"}
    return False


def _shorten(value: Any, limit: int = 160) -> str:
    rendered = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(rendered) <= limit:
        return rendered
    return rendered[: limit - 3] + "..."


def find_errors(
    input_file: str,
    lint_mode: str = DEFAULT_LINT_MODE,
    runtime_options: Optional[RuntimeOptions] = None,
) -> list[YAMLError]:
    """Return list of findings found in the given input_file

    If the file has Docassemble's optional Jinja2 preprocessor directive at the top,
    it is ignored and an empty list is returned.

    Args:
        input_file (str): Path to the YAML file to check.

    Returns:
        list[YAMLError]: List of findings found in the file.
    """
    with open(input_file, "r") as f:
        full_content = f.read()

    if full_content[:12] == "# use jinja\n":
        print()
        print(f"Ah Jinja! ignoring {input_file}")
        return []

    return find_errors_from_string(
        full_content,
        input_file=input_file,
        lint_mode=lint_mode,
        runtime_options=runtime_options,
    )


def find_style_findings_from_string(
    full_content: str,
    *,
    input_file: str | None = None,
    lint_mode: str = DEFAULT_LINT_MODE,
    runtime_options: Optional[RuntimeOptions] = None,
) -> list[Finding]:
    resolved_options = runtime_options or RuntimeOptions()
    if not resolved_options.style_enabled and not resolved_options.style_include_llm:
        resolved_options = replace(resolved_options, style_enabled=True)
    return [
        finding
        for finding in find_errors_from_string(
            full_content,
            input_file=input_file,
            lint_mode=lint_mode,
            runtime_options=resolved_options,
        )
        if finding.finding_class == FindingClass.STYLE
    ]


def _collect_yaml_files(
    paths: list[Path], include_default_ignores: bool = True
) -> list[Path]:
    from dayamlchecker.code_formatter import _collect_yaml_files as _formatter_collect

    return _formatter_collect(paths, include_default_ignores=include_default_ignores)


def process_file(
    input_file,
    lint_mode: str = DEFAULT_LINT_MODE,
    runtime_options: Optional[RuntimeOptions] = None,
) -> int:
    """
    Returns:
        int: the number of errors found in the input_file
    """
    for dumb_da_file in [
        "pgcodecache.yml",
        "title_documentation.yml",
        "documentation.yml",
        "docstring.yml",
        "example-list.yml",
        "examples.yml",
    ]:
        if input_file.endswith(dumb_da_file):
            print()
            print(f"ignoring {dumb_da_file}")
            return 0

    all_errors = find_errors(
        input_file, lint_mode=lint_mode, runtime_options=runtime_options
    )

    if len(all_errors) == 0:
        print(".", end="")
        return 0
    error_count = 0
    warning_count = 0
    info_count = 0
    for err in all_errors:
        if err.severity == "info":
            info_count += 1
        elif err.severity == "warning":
            warning_count += 1
        else:
            error_count += 1
    blocking_count = error_count + warning_count
    print()
    if info_count > 0:
        print(
            f"Found {len(all_errors)} issues ({error_count} errors, {warning_count} warnings, {info_count} infos):"
        )
    elif warning_count > 0:
        print(
            f"Found {len(all_errors)} issues ({error_count} errors, {warning_count} warnings):"
        )
    else:
        print(f"Found {len(all_errors)} errors:")
    for err in all_errors:
        print(f"{err}")
    return blocking_count


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Docassemble YAML files",
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="YAML files or directories to validate (directories are searched recursively)",
    )
    parser.add_argument(
        "--check-all",
        action="store_true",
        help=(
            "Do not ignore default directories during recursive search "
            "(.git*, .github*, build, dist, node_modules, sources)"
        ),
    )
    parser.add_argument(
        "--no-wcag",
        dest="wcag",
        action="store_false",
        help="Disable WCAG-style accessibility lint checks.",
    )
    parser.set_defaults(wcag=True)
    parser.add_argument(
        "--accessibility-error-on-widget",
        dest="accessibility_error_on_widgets",
        action="append",
        default=[],
        metavar="WIDGET",
        help=(
            "Treat a specific accessibility-sensitive widget as an error. "
            "Repeat to enable multiple widgets. Default: none"
        ),
    )
    parser.add_argument(
        "--style",
        action="store_true",
        help="Enable Assembly Line style lint checks.",
    )
    parser.add_argument(
        "--style-llm",
        action="store_true",
        help=(
            "Enable LLM-backed style findings. This also enables --style and "
            "uses an OpenAI-compatible API key from flags or environment."
        ),
    )
    parser.add_argument(
        "--openai-base-url",
        default=None,
        help=(
            "Base URL for an OpenAI-compatible API used by --style-llm "
            "(default: OPENAI_BASE_URL environment variable or the standard OpenAI API)"
        ),
    )
    parser.add_argument(
        "--openai-api-key",
        default=None,
        help="API key for --style-llm (default: OPENAI_API_KEY environment variable)",
    )
    parser.add_argument(
        "--openai-model",
        default=None,
        help="Model name for --style-llm (default: OPENAI_MODEL env var or gpt-4o-mini)",
    )
    parser.add_argument(
        "--url-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Check URLs in the selected question files and related "
            "template files (default: on)"
        ),
    )
    parser.add_argument(
        "--url-check-root",
        type=Path,
        default=None,
        help=(
            "Repository root for related template URL scanning "
            "(default: inferred from the YAML paths)"
        ),
    )
    parser.add_argument(
        "--url-check-timeout",
        type=int,
        default=10,
        help="HTTP timeout in seconds for each URL check (default: 10)",
    )
    parser.add_argument(
        "--url-check-ignore-urls",
        default="",
        help="Comma/newline-separated absolute URLs to ignore during URL checking",
    )
    parser.add_argument(
        "--url-check-skip-templates",
        dest="url_check_skip_documents",
        action="store_true",
        help="Skip checking URLs in related data/templates files",
    )
    parser.add_argument(
        "--url-check-skip-documents",
        dest="url_check_skip_documents",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--question-url-severity",
        "--yaml-url-severity",
        dest="yaml_url_severity",
        choices=("error", "warning", "ignore"),
        default="error",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--template-url-severity",
        dest="document_url_severity",
        choices=("error", "warning", "ignore"),
        default="warning",
        help="How to report broken or malformed URLs in template files (default: warning)",
    )
    parser.add_argument(
        "--document-url-severity",
        dest="document_url_severity",
        choices=("error", "warning", "ignore"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--unreachable-url-severity",
        choices=("error", "warning", "ignore"),
        default="warning",
        help="How to report URLs that could not be reached at all (default: warning)",
    )
    args = parser.parse_args(argv)

    lint_mode = ACCESSIBILITY_LINT_MODE if args.wcag else DEFAULT_LINT_MODE
    runtime_options = RuntimeOptions(
        accessibility_error_on_widgets=frozenset(
            widget.strip().lower()
            for widget in args.accessibility_error_on_widgets
            if widget.strip()
        ),
        style_enabled=args.style or args.style_llm,
        style_include_llm=args.style_llm,
        style_openai_base_url=args.openai_base_url,
        style_openai_api_key=args.openai_api_key,
        style_openai_model=args.openai_model,
    )

    yaml_files = _collect_yaml_files(
        args.files, include_default_ignores=not args.check_all
    )
    if not yaml_files:
        print("No YAML files found.", file=sys.stderr)
        return 1

    failed = False
    for input_file in yaml_files:
        error_count = process_file(
            str(input_file),
            lint_mode=lint_mode,
            runtime_options=runtime_options,
        )
        if error_count > 0:
            failed = True

    if args.url_check:
        url_check_root = (
            args.url_check_root.resolve()
            if args.url_check_root is not None
            else infer_url_check_root(yaml_files, fallback=Path.cwd())
        )
        url_check_result = run_url_check(
            root=url_check_root,
            question_files=yaml_files,
            package_dirs=infer_package_dirs(yaml_files),
            timeout=args.url_check_timeout,
            check_documents=not args.url_check_skip_documents,
            ignore_urls=parse_ignore_urls(args.url_check_ignore_urls),
            yaml_severity=args.yaml_url_severity,
            document_severity=args.document_url_severity,
            unreachable_severity=args.unreachable_url_severity,
        )
        print_url_check_report(url_check_result)
        if url_check_result.has_errors():
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
