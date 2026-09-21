"""The optional docassemble YAML preprocessor, isolated from validation."""

from pathlib import Path

from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment


def render_yaml(source: str, input_file: str | None = None) -> str:
    """Render local includes and ordinary Jinja without a docassemble server.

    Undefined values fail explicitly: silently selecting a branch based on
    missing server configuration could conceal errors in an interview.
    """
    env = SandboxedEnvironment(
        loader=FileSystemLoader(Path(input_file).parent) if input_file else None,
        undefined=StrictUndefined,
        autoescape=False,
    )
    return env.from_string(source).render()
