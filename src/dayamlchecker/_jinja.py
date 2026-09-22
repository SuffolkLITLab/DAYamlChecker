"""The optional docassemble YAML preprocessor, isolated from validation."""

from copy import copy
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryFile
from typing import Any
from uuid import uuid4

from jinja2 import (
    DictLoader,
    FileSystemLoader,
    Template,
    TemplateNotFound,
    Undefined,
    nodes,
)
from jinja2.compiler import CodeGenerator, Frame
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

# Applied before any template is compiled, including constant folding.
_RENDER_TIMEOUT = 5
_MAX_SOURCE_BYTES = 4 * 1024 * 1024
_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
_MEMORY_BYTES = 256 * 1024 * 1024
_CPU_SECONDS = 2
# Substituted for a value only the server can supply. A bare identifier keeps
# the rendered YAML parseable in every position a value can appear, including
# as a mapping key and inside a Python code block. The counter makes each one
# distinct so two unknown block ids do not collide.
_UNKNOWN_PREFIX = "dayc_unknown_"


_UNKNOWN_VALUE_RE = re.compile(rf"\b{_UNKNOWN_PREFIX}\d+\b")


def is_unknown_jinja_value(text: str) -> bool:
    """Report whether a placeholder for a server value appears in ``text``.

    Checks that resolve a name against the rest of the interview have nothing
    to resolve once a placeholder is involved, so they use this to stay quiet
    rather than describing our own substitution as an undefined variable.
    """
    return bool(_UNKNOWN_VALUE_RE.search(text))


def uses_jinja(source: str) -> bool:
    """Recognize only the documented first-line directive (LF, CRLF, or EOF)."""
    return re.match(r"# use jinja(?:\r?\n|$)", source) is not None


class JinjaRenderError(Exception):
    def __init__(
        self, message: str, filename: str | None = None, lineno: int | None = None
    ):
        super().__init__(message)
        self.filename = filename
        self.lineno = lineno


class _OfflineUndefined(Undefined):
    """Stand in for values supplied by docassemble's server configuration.

    Static checking has no access to ``jinja data`` or docassemble's built-in
    Jinja context.  Treat unknown values as empty instead of rejecting an
    otherwise valid interview.  Chained lookups and calls are supported because
    configuration values may be nested or exposed through helper objects.
    Arithmetic and comparison are too: a configuration value is often a count
    or a threshold, so ``{% if jinja_data.limit > 0 %}`` must select a branch
    rather than abort the whole file.
    """

    def _guard_sandbox_violation(self) -> None:
        if self._undefined_exception is SecurityError:
            self._fail_with_undefined_error()

    def _stay_empty(self, *args: object, **kwargs: object) -> "_OfflineUndefined":
        self._guard_sandbox_violation()
        return self

    def _compare_as_empty(self, other: object) -> bool:
        self._guard_sandbox_violation()
        return False

    def __str__(self) -> str:
        self._guard_sandbox_violation()
        return ""

    def __iter__(self):
        self._guard_sandbox_violation()
        return iter(())

    def __len__(self) -> int:
        self._guard_sandbox_violation()
        return 0

    def __bool__(self) -> bool:
        self._guard_sandbox_violation()
        return False

    def __getattr__(self, name: str) -> "_OfflineUndefined":
        self._guard_sandbox_violation()
        if name.startswith("_"):
            raise AttributeError(name)
        return self

    def __getitem__(self, key: object) -> "_OfflineUndefined":  # type: ignore[override]
        self._guard_sandbox_violation()
        return self

    def __call__(  # type: ignore[override]
        self, *args: object, **kwargs: object
    ) -> "_OfflineUndefined":
        self._guard_sandbox_violation()
        return self

    def __int__(self) -> int:  # type: ignore[override]
        self._guard_sandbox_violation()
        return 0

    def __float__(self) -> float:  # type: ignore[override]
        self._guard_sandbox_violation()
        return 0.0

    def __complex__(self) -> complex:  # type: ignore[override]
        self._guard_sandbox_violation()
        return 0j

    def __index__(self) -> int:
        # `range(config.count)` and friends need a real integer.
        self._guard_sandbox_violation()
        return 0

    def __abs__(self) -> "_OfflineUndefined":
        self._guard_sandbox_violation()
        return self

    def __round__(self, ndigits: int | None = None) -> "_OfflineUndefined":
        self._guard_sandbox_violation()
        return self

    def __format__(self, format_spec: str) -> str:
        # object.__format__ rejects any non-empty spec, so "{:>5}".format()
        # would fail on a value the server supplies.
        self._guard_sandbox_violation()
        return ""

    # Undefined maps each of these to _fail_with_undefined_error; an offline
    # value has to survive them instead.  Ordering is unknowable, so every
    # comparison against an absent value is false.
    __add__ = __radd__ = __sub__ = __rsub__ = _stay_empty  # type: ignore[assignment]
    __mul__ = __rmul__ = __truediv__ = __rtruediv__ = _stay_empty  # type: ignore[assignment]
    __floordiv__ = __rfloordiv__ = __mod__ = __rmod__ = _stay_empty  # type: ignore[assignment]
    __pow__ = __rpow__ = __pos__ = __neg__ = _stay_empty  # type: ignore[assignment]
    __lt__ = __le__ = __gt__ = __ge__ = _compare_as_empty  # type: ignore[assignment]


def _json_default(value: object) -> str:
    """Serialize offline values for ``| tojson``, which json cannot encode."""
    if isinstance(value, _OfflineUndefined):
        value._guard_sandbox_violation()
        return ""
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


@dataclass(frozen=True)
class MissingInclude:
    description: str
    file_name: str | None
    line_number: int


@dataclass(frozen=True)
class UnknownValue:
    """A rendered expression that depended on a value the server supplies."""

    name: str
    file_name: str | None
    line_number: int


class _IncludeCodeGenerator(CodeGenerator):
    def visit_Output(self, node: nodes.Output, frame: Frame) -> None:
        # Route each rendered expression through the environment so a value
        # the server would supply leaves a traceable placeholder instead of
        # vanishing. Literal text is left alone so it still folds at compile
        # time.
        node = copy(node)
        node.nodes = [
            (
                child
                if isinstance(child, (nodes.TemplateData, nodes.Const))
                else self._wrap_output(child)
            )
            for child in node.nodes
        ]
        super().visit_Output(node, frame)

    def _wrap_output(self, child: nodes.Expr) -> nodes.Expr:
        call = nodes.Call(
            nodes.EnvironmentAttribute("substitute_unknown"),
            [child, nodes.Const(self.filename), nodes.Const(child.lineno)],
            [],
            None,
            None,
        )
        call.set_lineno(child.lineno)
        return call

    def write_commons(self) -> None:
        super().write_commons()
        # The preamble binds `cond_expr_undefined = Undefined`, deliberately
        # using Jinja's strict type for the implicit else of an inline if.
        # Offline, `{{ "a" if server_value }}` has to behave like every other
        # missing value, so rebind it to the environment's type.
        self.writeline("cond_expr_undefined = environment.undefined")

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
    unknown_values: list[UnknownValue]
    unknown_count: int
    missing_marker: str

    def substitute_unknown(self, value: Any, filename: str | None, lineno: int) -> Any:
        if not isinstance(value, _OfflineUndefined):
            return value
        # A sandbox violation is a real finding, not an absent value.
        value._guard_sandbox_violation()
        name = value._undefined_name
        unknown = UnknownValue(str(name) if name else "expression", filename, lineno)
        if unknown not in self.unknown_values:
            self.unknown_values.append(unknown)
        self.unknown_count += 1
        return f"{_UNKNOWN_PREFIX}{self.unknown_count}"

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


def _render_yaml(
    source: str, input_file: str | None = None
) -> tuple[str, list[MissingInclude], list[UnknownValue]]:
    """Render YAML, blanking documents affected by unavailable includes.

    The result is best effort: missing templates may supply document separators
    or definitions. Preserve newlines so unaffected findings keep rendered line
    numbers. Values the server would supply are undefined here, so a branch on
    one is taken as if it were empty and only that branch is checked.
    """
    env = _PartialEnvironment(
        loader=(
            FileSystemLoader(Path(input_file).parent) if input_file else DictLoader({})
        ),
        undefined=_OfflineUndefined,
        autoescape=False,
    )
    env.policies["json.dumps_kwargs"] = {
        **env.policies["json.dumps_kwargs"],
        "default": _json_default,
    }
    env.missing_includes = []
    env.unknown_values = []
    env.unknown_count = 0
    env.missing_marker = f"DAYAMLCHECKER_MISSING_{uuid4().hex}"
    chunks = []
    size = 0
    for chunk in env.from_string(source).generate():
        size += len(chunk.encode("utf-8"))
        if size > _MAX_OUTPUT_BYTES:
            raise JinjaRenderError("Jinja rendered output exceeds 4 MiB limit")
        chunks.append(chunk)
    rendered = "".join(chunks)
    # Match the validator's document boundaries, retaining the separators.
    parts = re.split(r"(^--- *$)", rendered, flags=re.MULTILINE)
    rendered = "".join(
        "\n" * part.count("\n") if env.missing_marker in part else part
        for part in parts
    )
    return rendered, env.missing_includes, env.unknown_values


def render_yaml(
    source: str, input_file: str | None = None
) -> tuple[str, list[MissingInclude], list[UnknownValue]]:
    """Compile and render in a disposable, resource-limited worker."""
    if len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
        raise JinjaRenderError("Jinja source exceeds 4 MiB limit")
    # A file bounds parent memory even if the worker fails while serializing.
    with TemporaryFile() as output:
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).resolve())],
                input=json.dumps({"source": source, "input_file": input_file}).encode(),
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=_RENDER_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise JinjaRenderError(
                f"Jinja rendering exceeded {_RENDER_TIMEOUT} second time limit"
            ) from exc
        if completed.returncode:
            raise JinjaRenderError(
                "Jinja rendering worker stopped (CPU, memory, or response limit "
                f"may have been exceeded; exit {completed.returncode})"
            )
        output.seek(0)
        response = output.read(_MAX_RESPONSE_BYTES + 1)
    if len(response) > _MAX_RESPONSE_BYTES:
        raise JinjaRenderError("Jinja worker response exceeded size limit")
    result = json.loads(response)
    if "error" in result:
        raise JinjaRenderError(**result["error"])
    return (
        result["rendered"],
        [MissingInclude(**item) for item in result["missing"]],
        [UnknownValue(**item) for item in result["unknown"]],
    )


def _set_resource_limits() -> None:
    # Fail closed on platforms without OS-enforced limits; never fall back to
    # unbounded in-process rendering. The parent separately enforces wall time.
    try:
        import resource
    except ImportError as exc:
        raise JinjaRenderError(
            "Bounded Jinja rendering requires Unix resource limits"
        ) from exc
    limits = [
        (resource.RLIMIT_CPU, _CPU_SECONDS),
        (resource.RLIMIT_FSIZE, _MAX_RESPONSE_BYTES),
    ]
    # A fresh Darwin process reserves hundreds of GiB of virtual address space.
    # Lowering RLIMIT_AS below that existing reservation fails with EINVAL, so
    # retain the CPU, response-size, and parent wall-time bounds on macOS while
    # using the address-space cap on platforms where it is enforceable.
    if sys.platform != "darwin":
        limits.insert(0, (resource.RLIMIT_AS, _MEMORY_BYTES))
    for kind, limit in limits:
        _, hard = resource.getrlimit(kind)
        if hard != resource.RLIM_INFINITY:
            limit = min(limit, hard)
        resource.setrlimit(kind, (limit, limit))


def _worker() -> None:
    try:
        _set_resource_limits()
        request = json.load(sys.stdin)
        rendered, missing, unknown = _render_yaml(
            request["source"], request["input_file"]
        )
        result: dict[str, Any] = {
            "rendered": rendered,
            "missing": [asdict(item) for item in missing],
            "unknown": [asdict(item) for item in unknown],
        }
    except Exception as exc:
        filename = getattr(exc, "filename", None)
        lineno = getattr(exc, "lineno", None)
        if lineno is None:
            # Jinja rewrites runtime tracebacks into template-source frames.
            # Keep the innermost such frame, not a later Python library frame.
            tb = exc.__traceback__
            while tb is not None:
                if "__jinja_exception__" in tb.tb_frame.f_globals:
                    filename = tb.tb_frame.f_code.co_filename
                    lineno = tb.tb_lineno
                tb = tb.tb_next
        if filename == "<template>":
            filename = None
        message = (
            "Jinja rendering exceeded 256 MiB memory limit"
            if isinstance(exc, MemoryError)
            else str(exc)[:4096]
        )
        result = {"error": {"message": message, "filename": filename, "lineno": lineno}}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    _worker()
