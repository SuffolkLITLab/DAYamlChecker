# Each doc, apply this to each block
import re
import sys
# os and Path imports were used in a short-lived implementation; the CLI filtering approach is preferred
from typing import Optional
import yaml
from yaml.loader import SafeLoader
from mako.template import Template as MakoTemplate
from mako.exceptions import SyntaxException, CompileException
import esprima

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


__all__ = ["find_errors_from_string", "find_errors"]


# Ensure that if there's a space in the str, it's between quotes.
space_in_str = re.compile("^[^ ]*['\"].* .*['\"][^ ]*$")


class YAMLStr:
    """Should be a direct YAML string, not a list or dict"""

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [(f"{x} isn't a string", 1)]


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


import ast


class PythonText:
    """A full multiline python script. Should have valid python syntax. i.e. a code block

    This validator parses the Python using the stdlib ast module and reports
    SyntaxError with the line number from the parsed code so the caller can
    translate it into the YAML file line number.
    """

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [(f"code block must be a YAML string, is {type(x).__name__}", 1)]
            return
        try:
            ast.parse(x)
        except SyntaxError as ex:
            # ex.lineno gives line number within the code block
            lineno = ex.lineno or 1
            msg = ex.msg or str(ex)
            self.errors = [(f"Python syntax error: {msg}", lineno)]



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
    """Validator for js show if field modifier, checking:
    1) Valid JavaScript syntax (accounting for Mako expressions)
    2) Presence of at least one val() call
    3) That val() calls use quoted string literals for variable names
    """

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [(f"js show if must be a string, is {type(x).__name__}", 1)]
            return

        # First, check for val() presence
        if 'val(' not in x:
            self.errors.append((
                "js show if must contain at least one val() call to reference an on-screen field",
                1
            ))

        # Check for unquoted val() calls like val(some_var) instead of val("some_var")
        # Pattern: val( followed by something that isn't a quote
        unquoted_val_pattern = re.compile(r'val\s*\(\s*([a-zA-Z_][a-zA-Z0-9_.\[\]\'\"]*)\s*\)')
        for match in unquoted_val_pattern.finditer(x):
            content = match.group(1)
            # Check if it's not quoted (doesn't start with quote)
            if not (content.startswith('"') or content.startswith("'")):
                # Make sure it's not a valid unquoted pattern like val(something['key'])
                # Actually per the docs, val() must receive a literal string, so flag unquoted refs
                if '[' not in content and '.' not in content:
                    self.errors.append((
                        f'val() argument must be a quoted string literal, not "{content}". Use val("{content}") instead',
                        1
                    ))

        # Now check JavaScript syntax by removing Mako expressions first
        # Mako syntax is demarcated by ${ }
        js_to_check = x
        # Remove all ${ ... } mako expressions and replace with a safe literal
        mako_pattern = re.compile(r'\$\{[^}]*\}', re.DOTALL)
        js_to_check = mako_pattern.sub('true', js_to_check)

        # Use esprima to validate JavaScript syntax
        try:
            # parseScript throws esprima.Error on syntax problems
            esprima.parseScript(js_to_check, tolerant=False)
        except esprima.Error as ex:
            # We don't have precise YAML line mapping for the JS, so report at offset 1
            self.errors.append((
                f"Invalid JavaScript syntax in js show if: {ex}",
                1,
            ))


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
            if ':' not in x and ' ' not in x:  # Simple variable name
                # We can't validate this here without screen context
                # This will be validated at a higher level with fields context
                pass
            elif x.startswith('variable:') or x.startswith('code:'):
                # Malformed - these should be YAML dict format
                self.errors.append((
                    f'show if value "{x}" appears to be malformed. Use YAML dict syntax: show if: {{ variable: var_name, is: value }} or show if: {{ code: ... }}',
                    1
                ))
        elif isinstance(x, dict):
            # YAML dict form
            if 'variable' in x:
                # First method: show if: { variable: field_name, is: value }
                # Can only reference fields on the same screen - we'll validate in context
                pass
            elif 'code' in x:
                # Third method: show if: { code: python_code }
                # Validate Python syntax for the provided code block
                code_block = x.get('code')
                if not isinstance(code_block, str):
                    self.errors.append((
                        f'show if: code must be a YAML string',
                        1,
                    ))
                else:
                    try:
                        ast.parse(code_block)
                    except SyntaxError as ex:
                        lineno = ex.lineno or 1
                        msg = ex.msg or str(ex)
                        self.errors.append((
                            f'show if: code has Python syntax error: {msg}',
                            lineno,
                        ))
            else:
                self.errors.append((
                    f'show if dict must have either "variable" key or "code" key',
                    1
                ))


class DAPythonVar:
    """Things that need to be defined as a docassemble var, i.e. abc or x.y['a']"""

    def __init__(self, x):
        self.errors = []
        if not isinstance(x, str):
            self.errors = [(f"The python var needs to be a YAML string, is {x}", 1)]
        elif " " in x and not space_in_str.search(x):
            self.errors = [(f"The python var cannot have whitespace (is {x})", 1)]


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
            self.errors = [f"Objects block needs to be a list or a dict, is {x}"]
        # for entry in x:
        #   ...
        # if not isinstance(x, Union[list[dict[DAPythonVar, DAType]], dict[DAPythonVar, DAType]]):
        #  self.errors = [(f"Not objectAttrType isinstance! {x}", 1)]


class DAFields:
    def __init__(self, x):
        self.errors = []
        if not isinstance(x, list):
            self.errors = [(f"fields should be a list, is {x}", 1)]


# type notes what the value for that dictionary key is,

# More notes:
# mandatory can only be used on:
# question, code, objects, attachment, data, data from code

# TODO(brycew): composable validators! One validator that works with just lists of single entry dicts with a str as the key, and a DAPythonVar as the value, and another that expects a code block, then an OR validator that takes both and works with either.
# Works with smaller blocks, prevents a lot of duplicate nested code
big_dict = {
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
    "fields": {},
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
    "validation code": {},
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
    "interview help": {},
    "continue button field": {
        "type": DAPythonVar,
    },
    "show if": {
        "type": ShowIf,
    },
    "hide if": {
        "type": ShowIf,
    },
    "js show if": {
        "type": JSShowIf,
    },
    "js hide if": {
        "type": JSShowIf,
    },
    "enable if": {
        "type": ShowIf,
    },
    "disable if": {
        "type": ShowIf,
    },
    "js enable if": {
        "type": JSShowIf,
    },
    "js disable if": {
        "type": JSShowIf,
    },
    "disable others": {},
    "order": {},
}

# need a list of blocks; certain attributes imply certain blocks, and block out other things,
# like question and code

# Not all blocks are necessary: comment can be by itself, and attachment can be with question, or alone

# ordered by priority
# TODO: brycew: consider making required_attrs
types_of_blocks = {
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
    "sort reverse"
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
            return f"REAL ERROR: At {self.file_name}:{self.line_number}: {self.err_str}"
        return f"At {self.file_name}:{self.line_number}: {self.err_str}"


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
            if hasattr(key_node, 'value'):
                key = key_node.value
                if key in seen_keys:
                    # Raise YAML marked error so find_errors_from_string will
                    # capture this as a parsing error tied to a specific line.
                    raise yaml.error.MarkedYAMLError(
                        context=f"while constructing a mapping",
                        context_mark=node.start_mark,
                        problem=f"found duplicate key {key!r}",
                        problem_mark=key_node.start_mark,
                    )
                seen_keys.add(key)

        mapping = super(SafeLineLoader, self).construct_mapping(node, deep=deep)
        mapping["__line__"] = node.start_mark.line + 1
        return mapping


def validate_question_fields(fields_list, doc, base_line_number, input_file):
    """Validate show if/hide if and other field modifiers for a question's fields.
    
    Checks:
    1) Fields with show if/hide if: variable only work if the variable is on the same screen
    2) Fields that are hidden should not be directly referenced in mandatory blocks
    3) js show if/js hide if have valid JavaScript syntax and val() references
    """
    errors = []
    
    if not isinstance(fields_list, list):
        return errors
    
    # Extract field variable names that are defined on this screen
    screen_variables = set()
    hidden_variables = set()  # Track hidden variables
    
    for field_item in fields_list:
        if isinstance(field_item, dict):
            # Field dict can have variable name as value or label as key
            field_var_name = None
            for k, v in field_item.items():
                if isinstance(v, str) and k not in ['default', 'default value', 'hint', 'help', 
                                                       'label', 'datatype', 'choices', 'validation code',
                                                       'show if', 'hide if', 'js show if', 'js hide if',
                                                       'enable if', 'disable if', 'js enable if', 'js disable if']:
                    screen_variables.add(v)
                    field_var_name = v
                    break
            
            # Track if this field is hidden
            if field_var_name and ('show if' in field_item or 'hide if' in field_item or 
                                   'js show if' in field_item or 'js hide if' in field_item):
                hidden_variables.add(field_var_name)
    
    # Check each field for show if/hide if issues
    for i, field_item in enumerate(fields_list):
        if not isinstance(field_item, dict):
            continue
        
        field_var_name = None
        # Find the variable name for this field
        for k, v in field_item.items():
            if isinstance(v, str) and k not in ['default', 'default value', 'hint', 'help', 
                                                   'label', 'datatype', 'choices', 'validation code',
                                                   'show if', 'hide if', 'js show if', 'js hide if',
                                                   'enable if', 'disable if', 'js enable if', 'js disable if']:
                field_var_name = v
                break
        
        # Validate js show if
        if 'js show if' in field_item:
            validator = JSShowIf(field_item['js show if'])
            for err in validator.errors:
                errors.append(
                    YAMLError(
                        err_str=f"{err[0]}",
                        line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                        file_name=input_file,
                    )
                )
        
        # Validate js hide if
        if 'js hide if' in field_item:
            validator = JSShowIf(field_item['js hide if'])
            for err in validator.errors:
                errors.append(
                    YAMLError(
                        err_str=f"{err[0]}",
                        line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                        file_name=input_file,
                    )
                )
        
        # Validate js enable if
        if 'js enable if' in field_item:
            validator = JSShowIf(field_item['js enable if'])
            for err in validator.errors:
                errors.append(
                    YAMLError(
                        err_str=f"{err[0]}",
                        line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                        file_name=input_file,
                    )
                )
        
        # Validate js disable if
        if 'js disable if' in field_item:
            validator = JSShowIf(field_item['js disable if'])
            for err in validator.errors:
                errors.append(
                    YAMLError(
                        err_str=f"{err[0]}",
                        line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                        file_name=input_file,
                    )
                )
        
        # Check show if using variable reference (not code)
        if 'show if' in field_item:
            show_if = field_item['show if']
            # Dict form with variable check (client-side) or code check (server-side)
            if isinstance(show_if, dict):
                if 'variable' in show_if and 'code' not in show_if:
                    ref_var = show_if['variable']
                    if ref_var not in screen_variables:
                        errors.append(
                            YAMLError(
                                err_str=f'show if: variable: {ref_var} is not defined on this screen. Use show if: {{ code: ... }} instead for variables from previous screens',
                                line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                                file_name=input_file,
                            )
                        )
                elif 'code' in show_if:
                    code_block = show_if.get('code')
                    if not isinstance(code_block, str):
                        errors.append(
                            YAMLError(
                                err_str=f'show if: code must be a YAML string',
                                line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                                file_name=input_file,
                            )
                        )
                    else:
                        try:
                            ast.parse(code_block)
                        except SyntaxError as ex:
                            lineno = ex.lineno or 1
                            msg = ex.msg or str(ex)
                            errors.append(
                                YAMLError(
                                    err_str=f'show if: code has Python syntax error: {msg}',
                                    line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1) + lineno,
                                    file_name=input_file,
                                )
                            )
                else:
                    errors.append(
                        YAMLError(
                            err_str=f'show if dict must have either "variable" or "code"',
                            line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                            file_name=input_file,
                        )
                    )
            elif isinstance(show_if, str) and ':' not in show_if:
                # Shorthand form - must be a field on this screen
                if show_if not in screen_variables:
                    errors.append(
                        YAMLError(
                            err_str=f'show if: {show_if} is not defined on this screen. Use show if: {{ code: ... }} instead for variables from previous screens',
                            line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                            file_name=input_file,
                        )
                    )
        
        # Check hide if using variable reference (not code)
        if 'hide if' in field_item:
            hide_if = field_item['hide if']
            if isinstance(hide_if, dict):
                if 'variable' in hide_if and 'code' not in hide_if:
                    ref_var = hide_if['variable']
                    if ref_var not in screen_variables:
                        errors.append(
                            YAMLError(
                                err_str=f'hide if: variable: {ref_var} is not defined on this screen. Use hide if: {{ code: ... }} instead for variables from previous screens',
                                line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                                file_name=input_file,
                            )
                        )
                elif 'code' in hide_if:
                    code_block = hide_if.get('code')
                    if not isinstance(code_block, str):
                        errors.append(
                            YAMLError(
                                err_str=f'hide if: code must be a YAML string',
                                line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                                file_name=input_file,
                            )
                        )
                    else:
                        try:
                            ast.parse(code_block)
                        except SyntaxError as ex:
                            lineno = ex.lineno or 1
                            msg = ex.msg or str(ex)
                            errors.append(
                                YAMLError(
                                    err_str=f'hide if: code has Python syntax error: {msg}',
                                    line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1) + lineno,
                                    file_name=input_file,
                                )
                            )
                else:
                    errors.append(
                        YAMLError(
                            err_str=f'hide if dict must have either "variable" or "code"',
                            line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                            file_name=input_file,
                        )
                    )
            elif isinstance(hide_if, str) and ':' not in hide_if:
                # Shorthand form - must be a field on this screen
                if hide_if not in screen_variables:
                    errors.append(
                        YAMLError(
                            err_str=f'hide if: {hide_if} is not defined on this screen. Use hide if: {{ code: ... }} instead for variables from previous screens',
                            line_number=base_line_number + (doc.get("__line__", 1) if isinstance(doc, dict) else 1),
                            file_name=input_file,
                        )
                    )
    
    return errors


def find_errors_from_string(full_content: str, input_file: Optional[str] = None) -> list[YAMLError]:
    """Return list of YAMLError found in the given full_content string

    Args:
        full_content (str): Full YAML content as a string.
    Returns:
        list[YAMLError]: List of YAMLError instances found in the content.
    """
    all_errors = []

    if not input_file:
        input_file = "<string input>"

    exclusive_keys = [
        key
        for key in types_of_blocks.keys()
        if types_of_blocks[key].get("exclusive", True)
    ]

    line_number = 1
    for source_code in document_match.split(full_content):
        lines_in_code = sum(l == "\n" for l in source_code)
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
                    err_str=f"No possible types found: {doc}",
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
                        err_str=f"Too many types this block could be: {posb_types}",
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
                    err_str=f"Keys that shouldn't exist! {weird_keys}",
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
                            err_str=f"{err[0]}",
                            line_number=err[1] + doc["__line__"] + line_number,
                            file_name=input_file,
                        )
                    )
        
        # Additional field-level validation for show if/hide if
        if "fields" in doc and isinstance(doc["fields"], list):
            field_errors = validate_question_fields(doc["fields"], doc, line_number, input_file)
            all_errors.extend(field_errors)
        
        line_number += lines_in_code
    return all_errors


def find_errors(input_file: str) -> list[YAMLError]:
    """Return list of YAMLError found in the given input_file
       
    If the file has Docassemble's optional Jinja2 preprocessor directive at the top,
    it is ignored and an empty list is returned.

    Args:
        input_file (str): Path to the YAML file to check.

    Returns:
        list[YAMLError]: List of YAMLError instances found in the file.
    """
    with open(input_file, "r") as f:
        full_content = f.read()

    if full_content[:12] == "# use jinja\n":
        print()
        print(f"Ah Jinja! ignoring {input_file}")
        return []

    return find_errors_from_string(full_content, input_file=input_file)


def process_file(input_file):
    for dumb_da_file in [
        "pgcodecache.yml",
        "title_documentation.yml",
        "documentation.yml",
        "docstring.yml",
        "example-list.yml",
        "examples.yml"
    ]:
        if input_file.endswith(dumb_da_file):
            print()
            print(f"ignoring {dumb_da_file}")
            return

    all_errors = find_errors(input_file)

    if len(all_errors) == 0:
        print(".", end="")
        return
    print()
    print(f"Found {len(all_errors)} errors:")
    for err in all_errors:
        print(f"{err}")


def main():
    for input_file in sys.argv[1:]:
        process_file(input_file)


if __name__ == "__main__":
    main()
