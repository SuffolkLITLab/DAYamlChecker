"""The optional docassemble YAML preprocessor, isolated from validation."""

from copy import copy
from dataclasses import dataclass
from pathlib import Path
import re
from uuid import uuid4

from jinja2 import (
    DictLoader,
    FileSystemLoader,
    StrictUndefined,
    Template,
    TemplateNotFound,
    nodes,
)
from jinja2.compiler import CodeGenerator, Frame
from jinja2.sandbox import SandboxedEnvironment


@dataclass(frozen=True)
class MissingInclude:
    description: str
    file_name: str | None
    line_number: int


class _IncludeCodeGenerator(CodeGenerator):
    def visit_Include(self, node: nodes.Include, frame: Frame) -> None:
        # Wrap only include lookups. Imports and inheritance must still fail.
        node = copy(node)
        node.template = nodes.Call(
            nodes.EnvironmentAttribute("load_include"),
            [
                node.template,
                nodes.Const(self.name),
                nodes.Const(self.filename),
                nodes.Const(node.lineno),
            ],
            [],
            None,
            None,
        )
        node.template.set_lineno(node.lineno)
        super().visit_Include(node, frame)


class _PartialEnvironment(SandboxedEnvironment):
    code_generator_class = _IncludeCodeGenerator
    missing_includes: list[MissingInclude]
    missing_marker: str

    def load_include(
        self,
        name: str | Template | list[str | Template],
        parent: str | None,
        filename: str | None,
        lineno: int,
    ) -> Template:
        try:
            return self.get_or_select_template(name, parent)
        except TemplateNotFound as exc:
            # Try every candidate in an include list before substituting.
            missing = MissingInclude(str(exc), filename, lineno)
            if missing not in self.missing_includes:
                self.missing_includes.append(missing)
            return self.from_string(self.missing_marker)


def render_yaml(
    source: str, input_file: str | None = None
) -> tuple[str, list[MissingInclude]]:
    """Render YAML, blanking documents affected by unavailable includes.

    The result is best effort: missing templates may supply document separators
    or definitions. Preserve newlines so unaffected findings keep rendered line
    numbers. Missing server variables still fail instead of selecting a branch.
    """
    env = _PartialEnvironment(
        loader=(
            FileSystemLoader(Path(input_file).parent) if input_file else DictLoader({})
        ),
        undefined=StrictUndefined,
        autoescape=False,
    )
    env.missing_includes = []
    env.missing_marker = f"DAYAMLCHECKER_MISSING_{uuid4().hex}"
    rendered = env.from_string(source).render()
    # Match the validator's document boundaries, retaining the separators.
    parts = re.split(r"(^--- *$)", rendered, flags=re.MULTILINE)
    rendered = "".join(
        "\n" * part.count("\n") if env.missing_marker in part else part
        for part in parts
    )
    return rendered, env.missing_includes
