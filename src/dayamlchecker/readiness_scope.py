"""Conservative local include and bundle evidence. Never execute interview code."""

from __future__ import annotations

import ast
import re

from dayamlchecker.style import _include_candidates


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def question_files(root):
    return sorted(
        set(root.glob("docassemble/*/data/questions/**/*.yml"))
        | set(root.glob("docassemble/*/data/questions/**/*.yaml"))
    )


def template_path(question_file, ref):
    """Locate a literal template reference in the package that owns a question file."""
    package = next(p.parent for p in question_file.parents if p.name == "questions")
    return package / "templates" / ref


def doc_assignments(doc):
    """Return (name, expression) pairs and whether the block's code could be parsed."""
    expressions = []
    objects = doc.doc.get("objects", [])
    for obj in objects if isinstance(objects, list) else []:
        if isinstance(obj, dict):
            expressions.extend(
                (name, value) for name, value in obj.items() if isinstance(value, str)
            )
    code = doc.doc.get("code")
    if isinstance(code, str):
        try:
            expressions.extend(
                (ast.unparse(n.targets[0]), ast.unparse(n.value))
                for n in ast.walk(ast.parse(code))
                if isinstance(n, ast.Assign) and len(n.targets) == 1
            )
        except SyntaxError:
            return expressions, False
    return expressions, True


def local_scope(root, parsed, entrypoint_files=(), unparsed=()):
    """Trace local includes; `unparsed` files may hide their metadata and includes."""
    root = root.resolve()
    paths = {p.resolve(): docs for p, docs in parsed.items()}
    unparsed = {p.resolve() for p in unparsed}
    edges, unresolved = {}, {}
    for path, docs in paths.items():
        edges[path], unresolved[path] = set(), []
        for doc in docs:
            refs = doc.doc.get("include", [])
            for ref in (
                [refs]
                if isinstance(refs, str)
                else refs if isinstance(refs, list) else []
            ):
                if not isinstance(ref, str):
                    unresolved[path].append(str(ref))
                    continue
                target = next(
                    (
                        candidate.resolve()
                        for candidate in _include_candidates(ref, path)
                        if candidate.resolve() in paths
                    ),
                    None,
                )
                if target:
                    edges[path].add(target)
                else:
                    unresolved[path].append(ref)
    included = set().union(*edges.values()) if edges else set()
    if entrypoint_files:
        roots = [(root / p).resolve() for p in entrypoint_files]
        if any(p not in paths for p in roots):
            raise ValueError(
                "Choose entrypoints from this repository’s question YAML files."
            )
    else:
        roots = [
            p
            for p, docs in paths.items()
            if p not in included
            and (
                p in unparsed
                or any(
                    isinstance(d.doc.get("metadata"), dict)
                    and d.doc["metadata"].get("title")
                    for d in docs
                )
            )
        ]
        roots = roots or [p for p in paths if p not in included] or list(paths)
    entrypoints, closures, active = [], [], set()
    for entry in roots:
        closure, pending = set(), [entry]
        while pending:
            p = pending.pop()
            if p in closure:
                continue
            closure.add(p)
            pending.extend(edges[p])
        active.update(closure)
        closures.append(closure)
        entrypoints.append(
            {
                "file": str(entry.relative_to(root)),
                "local_files": sorted(str(p.relative_to(root)) for p in closure),
                "unresolved_includes": sorted(
                    {ref for p in closure for ref in unresolved[p]}
                ),
            }
        )
    # Keep a separate bundle graph for each entrypoint. Reused variable names in
    # unrelated interviews must not make their documents appear delivered here.
    template_states = {}
    for entry, closure in zip(entrypoints, closures):
        docs = [(p, d) for p in closure for d in paths[p]]
        bundles, attachments, uncertain = {}, [], False
        source = "\n".join(d.source_code for _, d in docs)
        for path, doc in docs:
            expressions, code_parsed = doc_assignments(doc)
            uncertain = uncertain or not code_parsed
            for name, value in expressions:
                if "ALDocumentBundle.using" not in value:
                    continue
                try:
                    call = ast.parse(value, mode="eval").body
                    elems = next(k.value for k in call.keywords if k.arg == "elements")
                    if not isinstance(elems, (ast.List, ast.Tuple)) or not all(
                        isinstance(n, ast.Name) for n in elems.elts
                    ):
                        uncertain = True
                        continue
                    members = {n.id for n in elems.elts}
                    # Multiple assignments/branches are possible, never select one.
                    bundles.setdefault(str(name), set()).update(members)
                except (SyntaxError, AttributeError, StopIteration):
                    uncertain = True
            if "attachment code" in doc.doc:
                uncertain = True
            # A question's own attachment is delivered without any bundle.
            direct = "question" in doc.doc
            for block in _walk(doc.doc):
                for key in ("pdf template file", "docx template file"):
                    ref = block.get(key)
                    if not isinstance(ref, str):
                        continue
                    if any(x in ref for x in ("${", "{{", ":")):
                        uncertain = True
                        continue
                    var = block.get("variable name", "")
                    if not isinstance(var, str) or not var:
                        uncertain = True
                    name = re.split(r"[.\[]", var)[0] if isinstance(var, str) else ""
                    target = template_path(path, ref).resolve()
                    if target.is_relative_to(root):
                        attachments.append(
                            (str(target.relative_to(root)), name, direct)
                        )
        used = set(
            re.findall(
                r"\b([A-Za-z_]\w*)(?:\[[^\]]*\])?\."
                r"(?:(?:download_list_html|send_button_html|send_button_to_html"
                r"|as_pdf|as_docx|as_zip|as_list|as_editable_list)\s*\("
                r"|(?:pdf|docx|rtf)\.\w)",
                source,
            )
        )
        pending = list(used)
        reached = set()
        while pending:
            name = pending.pop()
            if name in reached:
                continue
            reached.add(name)
            pending.extend(bundles.get(name, set()))
        if not used:
            uncertain = True
        # Unknown included libraries might modify a bundle after its declaration.
        for file, var, direct in attachments:
            state = (
                "potentially_delivered"
                if direct or var in reached
                else "unknown" if uncertain else "not_in_local_bundles"
            )
            template_states.setdefault(file, []).append(
                {"entrypoint": entry["file"], "status": state}
            )
    return {
        "selection": "explicit" if entrypoint_files else "inferred",
        "entrypoints": entrypoints,
        "active_local_files": sorted(str(p.relative_to(root)) for p in active),
        "templates": template_states,
        "limits": "Includes and literal bundles are overapproximations, not proof of an executed path. External libraries and dynamic membership remain unknown.",
    }


def template_exposure(scope, file):
    states = scope.get("templates", {}).get(file, [])
    if any(s["status"] == "potentially_delivered" for s in states):
        return "potentially_delivered"
    if states and all(s["status"] == "not_in_local_bundles" for s in states):
        return "not_in_local_bundles"
    return "unknown"
