"""Static release checks; conventions and uncertain inference remain advisory."""

from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any

from docx2python import docx2python
from jinja2 import Environment, meta
from pypdf import PdfReader

from dayamlchecker.accessibility import _extract_field_variable, _iter_fields
from dayamlchecker.docx_accessibility import (
    check_docx_accessibility,
    check_docx_review_markup,
)
from dayamlchecker.readiness_scope import (
    doc_assignments,
    template_exposure,
    template_path,
)
from dayamlchecker.style import ParsedInterviewDocument, _is_review_screen
from dayamlchecker.yaml_structure import _QUESTION_INPUT_KEYS


def check_policy(status: str) -> dict[str, Any]:
    return {
        "severity": {
            "blocked": "error",
            "needs_review": "warning",
            "warning": "warning",
        }.get(status, "info"),
        "release_gate": status in {"blocked", "needs_review"},
    }


def check_result(id: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": id,
        "status": status,
        **check_policy(status),
        "detail": detail,
        **extra,
    }


def naming_issues(name: str, *, repository: bool = False) -> list[str]:
    stem = name.removeprefix("docassemble-") if repository else Path(name).stem
    issues = []
    if re.search(r"\s", name):
        issues.append("Whitespace in name makes links and package handling harder.")
    if re.search(
        r"(?:^|[_ .-])(?:draft|copy|untitled|temp|tmp)(?:\d*|$)(?:[_ .-]|$)", stem, re.I
    ):
        issues.append("Name looks like a temporary or draft artifact.")
    if repository and re.fullmatch(
        r"(?:test|demo|project|myproject|newproject|form)\d*", stem, re.I
    ):
        issues.append("Repository name does not describe its purpose.")
    return issues


def static_checks(
    root: Path,
    parsed: dict[Path, list[ParsedInterviewDocument]],
    *,
    scope: dict,
    long_interview_screens: int = 10,
) -> list[dict]:
    checks = []
    filenames = [
        {"file": str(p.relative_to(root)), "issues": issues}
        for p in root.glob("docassemble/*/data/**/*")
        if p.is_file()
        if (issues := naming_issues(p.name))
    ]
    checks.append(
        check_result(
            "filenames",
            "warning" if filenames else "pass",
            "Naming is a maintainability advisory, not a release gate.",
            files=filenames,
        )
    )
    definitions = set()
    all_docs = [doc for docs in parsed.values() for doc in docs]
    all_source = "\n".join(d.source_code for d in all_docs)
    for doc in all_docs:
        for field in _iter_fields(doc.doc):
            variable = _extract_field_variable(field)
            if variable:
                definitions.add(re.split(r"[.\[]", variable)[0])
        for key in ("field", "yesno", "noyes", "yesnomaybe", "signature"):
            if isinstance(doc.doc.get(key), str):
                definitions.add(re.split(r"[.\[]", doc.doc[key])[0])
        objects = doc.doc.get("objects", [])
        if isinstance(objects, list):
            for obj in objects:
                if isinstance(obj, dict):
                    definitions.update(k for k in obj if k != "__line__")
        code = doc.doc.get("code")
        if isinstance(code, str):
            try:
                tree = ast.parse(code)
                definitions.update(
                    n.id
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                )
            except SyntaxError:
                pass
    checks.append(
        check_result(
            "project_setup",
            (
                "warning"
                if re.search(r"\b(?:users|other_parties)\b", all_source)
                and "ALPeopleList" not in all_source
                else "pass"
            ),
            "Weaver initialization is not required. Local ALPeopleList declarations are a maintainability hint; included libraries may supply them.",
        )
    )

    for entry in scope["entrypoints"]:
        docs = [
            d
            for p, ds in parsed.items()
            if str(p.relative_to(root)) in entry["local_files"]
            for d in ds
        ]
        complete = not entry["unresolved_includes"]
        screens = [
            d
            for d in docs
            if any(k in d.doc for k in _QUESTION_INPUT_KEYS)
            and not _is_review_screen(d)
        ]
        review = any(
            _is_review_screen(d)
            and (
                bool(d.doc.get("review"))
                or re.search(
                    r"(?:url_action|action_button_html|show_review_screen|\bedit\s*:)",
                    d.source_code,
                    re.I,
                )
            )
            for d in docs
        )
        long = len(screens) >= long_interview_screens
        if not screens or review:
            status = "pass"
        elif long and complete:
            status = "blocked"
        elif long:
            status = "needs_review"
        else:
            status = "warning"
        checks.append(
            check_result(
                "answer_review",
                status,
                "Missing review is a strong warning for short interviews and a release gate for long ones. Counts cover local declared input screens, not library questions or an executed path. Unresolved includes may provide review.",
                file=entry["file"],
                estimated_input_screens=len(screens),
                long_interview_threshold=long_interview_screens,
                review_detected=review,
                include_coverage_complete=complete,
            )
        )

    template_notes = []
    for path in sorted(root.glob("docassemble/*/data/templates/**/*")):
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".docx"}:
            continue
        record: dict[str, Any] = {"file": str(path.relative_to(root)), "notes": []}
        notes = record["notes"]
        try:
            if path.suffix.lower() == ".pdf":
                fields = PdfReader(path).get_fields() or {}
                labels = list(fields)
                multiline = [
                    name
                    for name, value in fields.items()
                    if int(value.get("/Ff", 0)) & 4096
                ]
                if multiline:
                    notes.append(
                        {
                            "kind": "overflow_unverified",
                            "fields": multiline,
                            "detail": "Check autosizing/overflow addenda statically; no populated interview was run.",
                        }
                    )
            else:
                with docx2python(path) as document:
                    text = document.text
                # docxtpl block tags add a paragraph/run/table prefix to Jinja.
                text = re.sub(r"\{%\s*(?:p|tr|tc|r)\s+", "{% ", text)
                text = re.sub(r"\{\{\s*r\s+", "{{ ", text)
                try:
                    labels = sorted(
                        meta.find_undeclared_variables(Environment().parse(text))
                    )
                except Exception:
                    labels = []
                    notes.append(
                        {
                            "kind": "template_syntax_unverified",
                            "detail": "Template-specific Jinja syntax needs review; static extraction is incomplete.",
                        }
                    )
                notes.extend(
                    {"kind": f.message_id, "detail": f.message}
                    for f in check_docx_accessibility(path)
                    + check_docx_review_markup(path)
                )
            suspect = []
            unmatched = []
            for label in labels:
                try:
                    expression = ast.parse(label, mode="eval").body
                    valid = isinstance(
                        expression, (ast.Name, ast.Attribute, ast.Subscript)
                    )
                except SyntaxError:
                    valid = False
                if not valid or re.fullmatch(
                    r"(?:Text|Check\s*Box|Field)[ _-]*\d+", label, re.I
                ):
                    suspect.append(label)
                elif (
                    path.suffix.lower() != ".pdf"
                    and label
                    not in {
                        "showifdef",
                        "defined",
                        "value",
                        "len",
                        "str",
                        "int",
                        "float",
                        "range",
                        "enumerate",
                        "zip",
                    }
                    and re.split(r"[.\[]", label)[0] not in definitions
                ):
                    unmatched.append(label)
            if suspect:
                notes.append({"kind": "template_labels", "fields": suspect})
            if unmatched:
                notes.append(
                    {
                        "kind": "mapping_unverified",
                        "fields": unmatched,
                        "detail": "No local definition found; includes or computed values may define these.",
                    }
                )
        except Exception as exc:
            notes.append({"kind": "unreadable_template", "detail": type(exc).__name__})
        if notes:
            template_notes.append(record)
    checks.append(
        check_result(
            "document_templates",
            "warning" if template_notes else "pass",
            "Static template inspection only. Label, mapping, markup, accessibility and overflow concerns are advisory.",
            templates=template_notes,
        )
    )

    delivery_errors, delivery_notes = [], []
    bundles = []
    for path, docs in parsed.items():
        for doc in docs:
            expressions, _ = doc_assignments(doc)
            for name, value in expressions:
                try:
                    expression = ast.parse(value, mode="eval").body
                except SyntaxError:
                    continue
                if not isinstance(expression, ast.Call) or not ast.unparse(
                    expression.func
                ).endswith("ALDocumentBundle.using"):
                    continue
                elements = next(
                    (kw.value for kw in expression.keywords if kw.arg == "elements"),
                    None,
                )
                record = {
                    "file": str(path.relative_to(root)),
                    "bundle": name,
                    "members": [],
                    "dynamic": not isinstance(elements, (ast.List, ast.Tuple)),
                }
                if isinstance(elements, (ast.List, ast.Tuple)):
                    record["members"] = [ast.unparse(item) for item in elements.elts]
                    unresolved = [
                        item.id
                        for item in elements.elts
                        if isinstance(item, ast.Name) and item.id not in definitions
                    ]
                    if unresolved or not elements.elts:
                        delivery_notes.append(
                            {
                                "file": record["file"],
                                "bundle": name,
                                "detail": "Literal bundle is empty or has members without local definitions; includes or later code may supply them.",
                                "unresolved_members": unresolved,
                            }
                        )
                else:
                    delivery_notes.append(
                        {
                            "file": record["file"],
                            "bundle": name,
                            "detail": "Bundle membership is computed and cannot be established from a literal list.",
                        }
                    )
                bundles.append(record)

    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in {"docx template file", "pdf template file"}:
                    refs = child if isinstance(child, list) else [child]
                    for ref in refs:
                        if not isinstance(ref, str) or any(
                            token in ref for token in ("${", "{{", ":")
                        ):
                            delivery_notes.append(
                                {
                                    "file": str(path.relative_to(root)),
                                    "reference": str(ref),
                                    "detail": "Dynamic or external template reference was not resolved.",
                                }
                            )
                        elif not template_path(path, ref).is_file():
                            delivery_errors.append(
                                {
                                    "file": str(path.relative_to(root)),
                                    "reference": ref,
                                    "detail": "Referenced local template is missing.",
                                }
                            )
                visit(child, path)
        elif isinstance(value, list):
            for child in value:
                visit(child, path)

    for path, docs in parsed.items():
        for doc in docs:
            visit(doc.doc, path)
    active_errors = []
    for error in delivery_errors:
        target = template_path(root / error["file"], error["reference"])
        relative = (
            str(target.resolve().relative_to(root.resolve()))
            if target.resolve().is_relative_to(root.resolve())
            else ""
        )
        if template_exposure(scope, relative) == "not_in_local_bundles":
            delivery_notes.append(
                {
                    **error,
                    "detail": "Unused local bundle template is missing. Check external or dynamic uses before removing it.",
                }
            )
        else:
            active_errors.append(error)
    delivery_errors = active_errors
    checks.append(
        check_result(
            "document_delivery",
            "blocked" if delivery_errors else "warning" if delivery_notes else "pass",
            "Missing literal local template files block delivery. Dynamic bundle membership, conditions and download behavior are not proven by this static check.",
            errors=delivery_errors,
            notes=delivery_notes,
            bundles=bundles,
        )
    )
    return checks
