# Each doc, apply this to each block
import ast
import argparse
from pathlib import Path
import re
import sys

from typing import Any, Optional
import yaml
from yaml.loader import SafeLoader
from mako.template import Template as MakoTemplate  # type: ignore[import-untyped]
from mako.exceptions import (  # type: ignore[import-untyped]
    SyntaxException,
    CompileException,
)
import esprima  # type: ignore[import-untyped]
from dayamlchecker._jinja import (
    JinjaWithoutHeaderError,
    _contains_jinja_syntax,
    _has_jinja_header,
    preprocess_jinja,
)

# TODO(brycew):
# * DA is fine with mixed case it looks like (i.e. Subquestion, vs subquestion)
# * what is "order"
# * can template and terms show up in same place?
# * can features and question show up in same place?
# * is "gathered" a valid attr?
# * handle "response"
# * labels above fields?
# [DONE] if "# use jinja" at top, process whole file with Jinja:
#   https://docassemble.org/docs/interviews.html#jinja2
#   Jinja files are pre-processed via preprocess_jinja() before checking,
#   and the formatter skips Jinja-syntax code blocks while formatting the rest.


__all__ = [
    "find_errors_from_string",
    "find_errors",
    "_collect_yaml_files",
    "JinjaWithoutHeaderError",
]


# Ensure that if there's a space in the str, it's between quotes.
space_in_str = re.compile("^[^ ]*['\"].* .*['\"][^ ]*$")


class YAMLStr:
    """Should be a direct YAML string, not a list or dict"""

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [(f"""{x} isn't a string""", 1)]


class MakoText:
    """A string that will be run through a Mako template from DA. Needs to have valid Mako template"""

    def __init__(self, x):
        self.errors = []
        try:
            self.template = MakoTemplate(
                x, strict_undefined=True, input_encoding="utf-8"
            )
        except SyntaxException as ex:
            self.errors = [(ex, ex.lineno)]
        except CompileException as ex:
            self.errors = [(ex, ex.lineno)]


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
                (f"""code block must be a YAML string, is {type(x).__name__}""", 1)
            ]
            return
        try:
            ast.parse(x)
        except SyntaxError as ex:
            # ex.lineno gives line number within the code block
            lineno = ex.lineno or 1
            msg = ex.msg or str(ex)
            self.errors = [(f"""Python syntax error: {msg}""", lineno)]


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
                (
                    "validation code does not call validation_error(); consider calling validation_error(...) to provide user-facing error messages",
                    1,
                )
            )


class PythonBool:
    """Some text that needs to explicitly be a python bool, i.e. True, False, bool(1), but not 1"""

    def __init__(self, x):
        self.errors = []
        pass


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
                (f"""{modifier_key} must be a string, is {type(x).__name__}""", 1)
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
                (
                    f"""Invalid JavaScript syntax in {modifier_key}: {ex}""",
                    getattr(ex, "lineNumber", 1) or 1,
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
                (
                    f"""{modifier_key} must contain at least one val() call to reference an on-screen field""",
                    1,
                )
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
                        (
                            f'{modifier_key} references val("{var_name}"), but "{var_name}" is not defined on this screen',
                            (call.get("loc", {}).get("start", {}).get("line", 1) or 1),
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
                (
                    f'val() argument must be a quoted string literal, not "{bad_arg}". Use val("...") or val(\'...\') instead',
                    (call.get("loc", {}).get("start", {}).get("line", 1) or 1),
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
                self.errors.append(
                    (
                        f'show if value "{x}" appears to be malformed. Use YAML dict syntax: show if: {{ variable: var_name, is: value }} or show if: {{ code: ... }}',
                        1,
                    )
                )
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
                    self.errors.append(
                        (
                            "show if: code must be a YAML string",
                            1,
                        )
                    )
                else:
                    try:
                        ast.parse(code_block)
                    except SyntaxError as ex:
                        lineno = ex.lineno or 1
                        msg = ex.msg or str(ex)
                        self.errors.append(
                            (
                                f"""show if: code has Python syntax error: {msg}""",
                                lineno,
                            )
                        )
            else:
                self.errors.append(
                    (
                        """show if dict must have either "variable" key or "code" key""",
                        1,
                    )
                )


class DAPythonVar:
    """Things that need to be defined as a docassemble var, i.e. abc or x.y['a']"""

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [(f"""The python var needs to be a YAML string, is {x}""", 1)]
        elif " " in x and not space_in_str.search(x):
            self.errors = [(f"""The python var cannot have whitespace (is {x})""", 1)]


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
            self.errors = [f"""Objects block needs to be a list or a dict, is {x}"""]
        # for entry in x:
        #   ...
        # if not isinstance(x, Union[list[dict[DAPythonVar, DAType]], dict[DAPythonVar, DAType]]):
        #  self.errors = [(f"""Not objectAttrType isinstance! {x}""", 1)]


class DAFields:
    modifier_keys = {
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

    js_modifier_keys = ("js show if", "js hide if", "js enable if", "js disable if")
    py_modifier_keys = ("show if", "hide if")

    # Keys that are valid at the field-item level (i.e. inside a single field dict).
    # When `fields` is written as a bare dict (single-field shorthand rather than a
    # list), at least one of these keys must be present for it to look like a valid
    # field descriptor rather than a malformed code-reference dict.
    _field_item_keys = modifier_keys | {
        "field",
        "input type",
        "note",
        "html",
        "raw html",
        "address autocomplete",
        "object",
        "object multiselect",
        "object radio",
        "uncheck others",
        "shuffle",
        "required",
        "read only",
        "min",
        "max",
    }

    def __init__(self, x):
        self.errors = []
        if isinstance(x, dict):
            if "code" in x:
                # Code-reference form: fields: {code: some_python_list_var}
                if not isinstance(x.get("code"), str):
                    self.errors = [
                        (
                            f"""fields: code must be a YAML string, is {type(x.get("code")).__name__}""",
                            1,
                        )
                    ]
                return
            # Single-field shorthand: fields is a bare dict describing one field.
            # Docassemble allows omitting the surrounding list when there is exactly
            # one field.  Accept it silently if it has at least one recognised key;
            # otherwise flag it so genuinely broken dicts are still caught.
            if x.keys() & self._field_item_keys:
                return
            self.errors = [(f'fields dict must have "code" key, is {x}', 1)]
            return
        if not isinstance(x, list):
            self.errors = [(f"""fields should be a list or dict, is {x}""", 1)]
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
                        (
                            f"""{modifier_key}: variable must be a string, got {type(ref_var).__name__}""",
                            self._line_for(field_item),
                        )
                    )
                elif not references_screen_variable(ref_var):
                    self.errors.append(
                        (
                            f"""{modifier_key}: variable: {ref_var} is not defined on this screen. Use {modifier_key}: {{ code: ... }} instead for variables from previous screens""",
                            self._line_for(field_item),
                        )
                    )
            elif "code" in modifier_value:
                validator = PythonText(modifier_value.get("code"))
                for err in validator.errors:
                    self.errors.append(
                        (
                            f"""{modifier_key}: code has {err[0].lower()}""",
                            self._line_for(field_item, err[1]),
                        )
                    )
            else:
                self.errors.append(
                    (
                        f'{modifier_key} dict must have either "variable" or "code"',
                        self._line_for(field_item),
                    )
                )
        elif isinstance(modifier_value, str) and ":" not in modifier_value:
            if not references_screen_variable(modifier_value):
                self.errors.append(
                    (
                        f"""{modifier_key}: {modifier_value} is not defined on this screen. Use {modifier_key}: {{ code: ... }} instead for variables from previous screens""",
                        self._line_for(field_item),
                    )
                )

    def _validate_field_modifiers(self, fields_list):
        screen_variables = set()
        for field_item in fields_list:
            field_var_name = self._extract_field_name(field_item)
            if field_var_name:
                screen_variables.add(field_var_name)

        for field_item in fields_list:
            if not isinstance(field_item, dict):
                continue

            for js_key in self.js_modifier_keys:
                if js_key in field_item:
                    validator = JSShowIf(
                        field_item[js_key],
                        modifier_key=js_key,
                        screen_variables=screen_variables,
                    )
                    for err in validator.errors:
                        self.errors.append((err[0], self._line_for(field_item, err[1])))

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
    "initial": {},
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


class YAMLError:
    def __init__(
        self,
        *,
        err_str: str,
        line_number: int,
        file_name: str,
        experimental: bool = True,
    ):
        self.err_str = err_str
        self.line_number = line_number
        self.file_name = file_name
        self.experimental = experimental
        pass

    def __str__(self):
        if not self.experimental:
            return f"""REAL ERROR: At {self.file_name}:{self.line_number}: {self.err_str}"""
        return f"""At {self.file_name}:{self.line_number}: {self.err_str}"""


class SafeLineLoader(SafeLoader):
    """https://stackoverflow.com/questions/13319067/parsing-yaml-return-with-line-number"""

    def construct_mapping(self, node, deep=False):
        # Detect duplicate keys in the mapping node and raise a helpful
        # MarkedYAMLError with the problem and line information. PyYAML
        # otherwise allows duplicate keys and silently takes the last
        # occurrence, which is not ideal for our linter.
        seen_keys = set()
        for key_node, _ in node.value:
            # Only check scalar keys
            if hasattr(key_node, "value"):
                key = key_node.value
                if key in seen_keys:
                    # Raise YAML marked error so find_errors_from_string will
                    # capture this as a parsing error tied to a specific line.
                    raise yaml.error.MarkedYAMLError(
                        context="""while constructing a mapping""",
                        context_mark=node.start_mark,
                        problem=f"""found duplicate key {key!r}""",
                        problem_mark=key_node.start_mark,
                    )
                seen_keys.add(key)

        mapping = super(SafeLineLoader, self).construct_mapping(node, deep=deep)
        mapping["__line__"] = node.start_mark.line + 1
        return mapping


def find_errors_from_string(
    full_content: str, input_file: Optional[str] = None
) -> list[YAMLError]:
    """Return list of YAMLError found in the given full_content string

    Args:
        full_content (str): Full YAML content as a string.
    Returns:
        list[YAMLError]: List of YAMLError instances found in the content.
    """
    all_errors = []

    if not input_file:
        input_file = "<string input>"

    # Check for Jinja syntax before attempting YAML parsing, since Jinja
    # constructs are not valid YAML and would cause parse errors.
    if _contains_jinja_syntax(full_content):
        if _has_jinja_header(full_content):
            # Valid Jinja file: pre-process through Jinja2 then check the
            # rendered output as normal YAML.
            rendered, render_errors = preprocess_jinja(full_content)
            if render_errors:
                return [
                    YAMLError(
                        err_str=e,
                        line_number=1,
                        file_name=input_file,
                        experimental=False,
                    )
                    for e in render_errors
                ]
            # Strip the '# use jinja' header from the rendered output so the
            # recursive call does not re-enter this branch.
            _, _sep, rendered_body = rendered.partition("\n")
            return find_errors_from_string(rendered_body, input_file=input_file)
        return [
            YAMLError(
                err_str=(
                    "File contains Jinja syntax but is missing '# use jinja' on the "
                    "first line. Per docassemble documentation, add '# use jinja' as "
                    "the very first line to enable Jinja2 processing, or remove the "
                    "Jinja syntax from the file."
                ),
                line_number=1,
                file_name=input_file,
                experimental=False,
            )
        ]

    exclusive_keys = [
        key
        for key in types_of_blocks.keys()
        if types_of_blocks[key].get("exclusive", True)
    ]

    line_number = 1
    for source_code in document_match.split(full_content):
        lines_in_code = sum(source_line == "\n" for source_line in source_code)
        source_code = remove_trailing_dots.sub("", source_code)
        source_code = fix_tabs.sub("  ", source_code)
        try:
            doc = yaml.load(source_code, SafeLineLoader)
        except Exception as errMess:
            if isinstance(errMess, yaml.error.MarkedYAMLError):
                if errMess.context_mark is not None:
                    errMess.context_mark.line += line_number - 1
                if errMess.problem_mark is not None:
                    errMess.problem_mark.line += line_number - 1
            all_errors.append(
                YAMLError(
                    err_str=str(errMess),
                    line_number=line_number,
                    file_name=input_file,
                    experimental=False,
                )
            )
            line_number += lines_in_code
            continue

        if doc is None:
            # Just YAML comments, that's fine
            line_number += lines_in_code
            continue
        any_types = [block for block in types_of_blocks.keys() if block in doc]
        if len(any_types) == 0:
            all_errors.append(
                YAMLError(
                    err_str=f"""No possible types found: {doc}""",
                    line_number=line_number,
                    file_name=input_file,
                )
            )
        posb_types = [block for block in exclusive_keys if block in doc]
        if len(posb_types) > 1:
            if len(posb_types) == 2 and posb_types[1] in (
                types_of_blocks[posb_types[0]].get("partners") or []
            ):
                pass
            else:
                all_errors.append(
                    YAMLError(
                        err_str=f"""Too many types this block could be: {posb_types}""",
                        line_number=line_number,
                        file_name=input_file,
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
                YAMLError(
                    err_str=f"""Keys that shouldn't exist! {weird_keys}""",
                    line_number=line_number,
                    file_name=input_file,
                    experimental=False,
                )
            )
        for key in doc.keys():
            if key in big_dict and "type" in big_dict[key]:
                test = big_dict[key]["type"](doc[key])
                for err in test.errors:
                    all_errors.append(
                        YAMLError(
                            err_str=f"""{err[0]}""",
                            line_number=err[1] + doc["__line__"] + line_number,
                            file_name=input_file,
                        )
                    )

        line_number += lines_in_code
    return all_errors


def find_errors(input_file: str) -> list[YAMLError]:
    """Return list of YAMLError found in the given input_file

    If the file starts with the '# use jinja' header it is skipped and an empty
    list is returned.  If Jinja syntax is detected *without* that header a
    YAMLError is returned explaining the problem.

    Args:
        input_file (str): Path to the YAML file to check.

    Returns:
        list[YAMLError]: List of YAMLError instances found in the file.
    """
    with open(input_file, "r") as f:
        full_content = f.read()

    return find_errors_from_string(full_content, input_file=input_file)


def _collect_yaml_files(
    paths: list[Path], include_default_ignores: bool = True
) -> list[Path]:
    from dayamlchecker.code_formatter import _collect_yaml_files as _formatter_collect

    return _formatter_collect(paths, include_default_ignores=include_default_ignores)


def process_file(
    input_file,
    minimal: bool = False,
    quiet: bool = False,
    display_path: str | None = None,
) -> str:
    """Process a single file and report its validation status.

    Args:
        input_file: Path to the YAML file to check.
        minimal: If True, use a compact output format. Successful files print
            a single character ('.' for normal files or 'j' for Jinja files),
            and errors trigger a brief summary followed by each error message.
        quiet: If True, suppress output for successful and skipped files.
            Errors are still printed unless combined with other output handling.
        display_path: Optional path string to use in output instead of the
            full ``input_file`` path (e.g. a relative path).

    Returns:
        A string indicating the result of processing:
        - "ok": The file was checked and no errors were found.
        - "error": The file was checked and one or more errors were found.
        - "skipped": The file was not checked because it matches a known
          pattern of files to ignore.
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
            if not minimal and not quiet:
                print(f"skipped: {display_path or input_file}")
            return "skipped"

    with open(input_file, "r") as f:
        full_content = f.read()

    is_jinja = _has_jinja_header(full_content)

    all_errors = find_errors_from_string(
        full_content, input_file=display_path or input_file
    )

    if len(all_errors) == 0:
        if minimal:
            print("j" if is_jinja else ".", end="")
        elif not quiet:
            label = "ok (jinja)" if is_jinja else "ok"
            print(f"{label}: {display_path or input_file}")
        return "ok"

    if minimal:
        print()
        print(
            f"""Found {len(all_errors)} errors{" (in Jinja-preprocessed file)" if is_jinja else ""}:"""
        )
        for err in all_errors:
            print(f"{err}")
    else:
        jinja_note = " (jinja)" if is_jinja else ""
        print(f"errors ({len(all_errors)}){jinja_note}: {display_path or input_file}")
        for err in all_errors:
            print(f"  {err}")
    return "error"


def main() -> int:
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
            "(.git*, .github*, sources)"
        ),
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "-m",
        "--minimal",
        action="store_true",
        help="Show compact dot/letter progress instead of per-file lines",
    )
    output_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress all output except errors",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Do not print the summary line after processing",
    )
    args = parser.parse_args()

    # Precompute resolved base dirs for relative path display
    base_dirs = [p.resolve() if p.is_dir() else p.resolve().parent for p in args.files]

    def _display(file_path: Path) -> Path:
        resolved = file_path.resolve()
        for base in base_dirs:
            try:
                return resolved.relative_to(base)
            except ValueError:
                continue
        return resolved

    yaml_files = _collect_yaml_files(
        args.files, include_default_ignores=not args.check_all
    )
    if not yaml_files:
        print("No YAML files found.", file=sys.stderr)
        return 1

    files_ok = 0
    files_error = 0
    files_skipped = 0

    for input_file in yaml_files:
        status = process_file(
            str(input_file),
            minimal=args.minimal,
            quiet=args.quiet,
            display_path=str(_display(input_file)),
        )
        if status == "ok":
            files_ok += 1
        elif status == "error":
            files_error += 1
        else:
            files_skipped += 1

    if args.minimal:
        print()  # terminate dot line

    if not args.quiet and not args.no_summary:
        total = files_ok + files_error + files_skipped
        summary_parts = []
        if files_ok:
            summary_parts.append(f"""{files_ok} ok""")
        if files_error:
            summary_parts.append(f"""{files_error} errors""")
        if files_skipped:
            summary_parts.append(f"""{files_skipped} skipped""")
        if not summary_parts:
            summary_parts.append("0 files processed")
        print(f"""Summary: {", ".join(summary_parts)} ({total} total)""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
