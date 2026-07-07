from __future__ import annotations

import ast
from typing import Any

from dayamlchecker import messages
from dayamlchecker.messages import (
    FindingClass,
    MessageDefinition,
    Severity,
    draft,
)

PYTHON_CODE_FUNCTION_DEF = "python_code_function_def"


class _FunctionDefFinder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.first_function: ast.FunctionDef | ast.AsyncFunctionDef | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.first_function is None:
            self.first_function = node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self.first_function is None:
            self.first_function = node


def _register_message_definition() -> None:
    messages.MESSAGE_DEFINITIONS.setdefault(
        PYTHON_CODE_FUNCTION_DEF,
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


def _first_function_def(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    finder = _FunctionDefFinder()
    finder.visit(tree)
    return finder.first_function


def install() -> None:
    """Register the warning and attach it to the existing code block validator."""
    _register_message_definition()

    from dayamlchecker import yaml_structure

    if getattr(yaml_structure.PythonText, "_warns_on_function_def", False):
        return

    base_python_text = yaml_structure.PythonText

    class PythonTextWithFunctionDefWarning(base_python_text):  # type: ignore[misc, valid-type]
        _warns_on_function_def = True

        def __init__(self, x: Any) -> None:
            super().__init__(x)
            if self.errors or not isinstance(x, str):
                return
            function_node = _first_function_def(x)
            if function_node is None:
                return
            self.errors.append(
                draft(
                    PYTHON_CODE_FUNCTION_DEF,
                    line_number=getattr(function_node, "lineno", 1) or 1,
                    function_name=function_node.name,
                )
            )

    yaml_structure.PythonText = PythonTextWithFunctionDefWarning
    yaml_structure.big_dict["code"]["type"] = PythonTextWithFunctionDefWarning
