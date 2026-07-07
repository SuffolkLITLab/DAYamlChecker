import ast
from typing import Any

from dayamlchecker import messages as _messages
from dayamlchecker.messages import (
    Finding,
    FindingClass,
    MessageDefinition,
    Severity,
    draft,
)
from dayamlchecker.yaml_structure import (
    RuntimeOptions,
    find_errors,
    find_errors_from_string,
    find_style_findings_from_string,
)

_PYTHON_CODE_FUNCTION_DEF = "python_code_function_def"


def _install_code_def_warning() -> None:
    _messages.MESSAGE_DEFINITIONS.setdefault(
        _PYTHON_CODE_FUNCTION_DEF,
        MessageDefinition(
            code="WG123",
            severity=Severity.WARNING,
            finding_class=FindingClass.GENERAL,
            summary="Code block defines a Python function",
            template=(
                "code block defines function `{function_name}`; move reusable "
                "helper functions to a Python module instead"
            ),
        ),
    )

    from dayamlchecker import yaml_structure as _yaml_structure

    if getattr(_yaml_structure.PythonText, "_warns_on_function_def", False):
        return

    base_python_text = _yaml_structure.PythonText

    class PythonTextWithFunctionDefWarning(base_python_text):  # type: ignore[misc, valid-type]
        _warns_on_function_def = True

        def __init__(self, x: Any) -> None:
            super().__init__(x)
            if self.errors or not isinstance(x, str):
                return
            try:
                tree = ast.parse(x)
            except SyntaxError:
                return
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.errors.append(
                        draft(
                            _PYTHON_CODE_FUNCTION_DEF,
                            line_number=getattr(node, "lineno", 1) or 1,
                            function_name=node.name,
                        )
                    )
                    break

    _yaml_structure.PythonText = PythonTextWithFunctionDefWarning
    _yaml_structure.big_dict["code"]["type"] = PythonTextWithFunctionDefWarning


_install_code_def_warning()
del _install_code_def_warning

__all__ = [
    "Finding",
    "FindingClass",
    "RuntimeOptions",
    "find_errors",
    "find_errors_from_string",
    "find_style_findings_from_string",
]
