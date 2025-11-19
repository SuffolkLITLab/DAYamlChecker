# Each doc, apply this to each block
import re
import sys
# os and Path imports were used in a short-lived implementation; the CLI filtering approach is preferred
from typing import Optional
import yaml
from yaml.loader import SafeLoader
from mako.template import Template as MakoTemplate
from mako.exceptions import SyntaxException, CompileException

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


class PythonText:
    """A full multiline python script. Should have valid python syntax. i.e. a code block"""

    def __init__(self, x):
        self.errors = []
        pass


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
        mapping = super(SafeLineLoader, self).construct_mapping(node, deep=deep)
        mapping["__line__"] = node.start_mark.line + 1
        return mapping


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
                    err_str=errMess,
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
