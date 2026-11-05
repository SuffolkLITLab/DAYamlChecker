"""Evidence-based publication pre-flight; never infer legal or runtime approval."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, replace
import json
import hashlib
import sys
from pathlib import Path
from typing import Any

from dayamlchecker.readiness_report import markdown_report
from dayamlchecker.readiness_research import (
    DEFAULT_MODEL,
    ResearchOptions,
    add_research_arguments,
    options_from_args,
    research_readiness,
)
from dayamlchecker.readiness_review import review_view
from dayamlchecker.readiness_scope import local_scope, question_files
from dayamlchecker.readiness_static import check_policy, check_result, static_checks
from dayamlchecker.style import _find_metadata
from dayamlchecker.readiness_github import github_publication
from dayamlchecker.readiness_playground import (
    PlaygroundOptions,
    PlaygroundError,
    scan_playgrounds,
)
from dayamlchecker.messages import Severity, FindingClass, MessageId
from dayamlchecker.yaml_structure import (
    RuntimeOptions,
    find_errors_from_string,
    parse_interview_documents,
)

from dayamlchecker.readiness_ai_review import (
    AIReviewOptions,
    review_candidates,
    apply_ai_review,
)

CHECKLIST_URL = (
    "https://assemblyline.suffolklitlab.org/docs/authoring/weaver/authoring_checklist/"
)
MATURITY_URL = "https://projects.suffolklitlab.org/legal-tech-class/docs/legal-tech-overview/maturity-model/"
EXIT_CODES = {"pass": 0, "blocked": 1, "needs_review": 2}
# These are project evidence requirements, not an official Court Forms Online policy.
REVIEWS = {
    "legal_review": (
        "1",
        "Subject matter expert reviewed legal accuracy and omissions",
    ),
    "plain_language_review": (
        "1.5",
        "Question design and explanations reviewed for comprehension",
    ),
    "interview_flow_review": (
        "2",
        "Interview branches, eligibility exits and answer editing reviewed statically",
    ),
    "publication_review": (
        "2",
        "Maintainer approved metadata, jurisdiction, eligibility, and publication",
    ),
}


def add_readiness_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("readiness sources and release policy")
    group.add_argument(
        "--readiness-ai-review",
        action="store_true",
        help="Opt in to one paid AI second opinion on candidate findings; preserves raw results.",
    )
    group.add_argument("--readiness-review-model", default=DEFAULT_MODEL)
    group.add_argument("--readiness-review-timeout", type=int, default=180)
    group.add_argument("--readiness-review-max-candidates", type=int, default=40)
    group.add_argument(
        "--readiness-format",
        choices=("json", "markdown"),
        default="json",
        help="Report format: machine-readable JSON or an instructor-facing Markdown report.",
    )
    group.add_argument(
        "--readiness-entrypoint",
        action="append",
        default=[],
        help="Question YAML path relative to the repo; repeat to select published entrypoints.",
    )
    group.add_argument(
        "--long-interview-screens",
        type=int,
        default=10,
        help="Estimated input-screen count requiring answer review (default: 10).",
    )
    group.add_argument(
        "--readiness-github",
        action="store_true",
        help="Check the exact local commit and working tree against GitHub (read-only).",
    )
    group.add_argument("--github-repository", help="GitHub owner/repository override")
    group.add_argument(
        "--github-ref", help="Published branch/ref (default: current branch)"
    )
    group.add_argument(
        "--playground-server",
        help="Read-only docassemble Playground source, instead of a local repository",
    )
    group.add_argument(
        "--playground-user",
        help="Author email/username or numeric user ID; defaults to API key owner",
    )
    group.add_argument(
        "--playground-project",
        action="append",
        default=[],
        help="Project to scan; repeatable, defaults to all projects",
    )


def readiness_options_from_args(args, parser) -> dict:
    if args.long_interview_screens < 1:
        parser.error("--long-interview-screens must be positive")
    if (args.github_repository or args.github_ref) and not args.readiness_github:
        parser.error("--github-repository and --github-ref require --readiness-github")
    if (args.playground_user or args.playground_project) and not args.playground_server:
        parser.error("Playground user/project requires --playground-server")
    if args.playground_server and args.readiness_github:
        parser.error(
            "Playground snapshots have no Git commit; check GitHub publication separately on a checkout"
        )
    ai_review = None
    if args.readiness_ai_review:
        try:
            ai_review = AIReviewOptions(
                model=args.readiness_review_model,
                timeout=args.readiness_review_timeout,
                max_candidates=args.readiness_review_max_candidates,
                base_url=args.openai_base_url,
                api_key=args.openai_api_key,
            )
        except ValueError as exc:
            parser.error(str(exc))
    return {
        "ai_review": ai_review,
        "report_format": args.readiness_format,
        "entrypoint_files": tuple(args.readiness_entrypoint),
        "style_options": RuntimeOptions(
            style_enabled=True,
            style_include_llm=getattr(args, "style_llm", False),
            style_review_level=getattr(args, "style_review_level", "precision"),
            style_openai_model=getattr(args, "openai_model", None),
            style_openai_base_url=args.openai_base_url,
            style_openai_api_key=args.openai_api_key,
            spellcheck=None,
        ),
        "long_interview_screens": args.long_interview_screens,
        "github": args.readiness_github,
        "github_repository": args.github_repository,
        "github_ref": args.github_ref,
        "playground": (
            PlaygroundOptions(
                args.playground_server,
                args.playground_user,
                tuple(args.playground_project),
            )
            if args.playground_server
            else None
        ),
    }


def _has_local_default(finding, parsed):
    if finding.message_id != MessageId.INTERVIEW_ORDER_UNMATCHED_GUARD:
        return False
    field = finding.context.get("field_name")
    block = finding.context.get("repair_context", {}).get("block_index")
    for doc in parsed.get(Path(finding.file_name or ""), []):
        if doc.index != block or not isinstance(doc.doc.get("code"), str):
            continue
        try:
            tree = ast.parse(doc.doc["code"])
        except SyntaxError:
            continue
        refs = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, (ast.Name, ast.Attribute, ast.Subscript))
            and isinstance(n.ctx, ast.Load)
            and ast.unparse(n) == field
        ]
        if refs and any(
            isinstance(n, (ast.Name, ast.Attribute, ast.Subscript))
            and isinstance(n.ctx, ast.Store)
            and ast.unparse(n) == field
            and n.lineno < min(refs)
            for n in ast.walk(tree)
        ):
            return True
    return False


def publication_readiness(
    root: Path,
    *,
    evidence: dict[str, Any] | None = None,
    research: ResearchOptions | None = None,
    ai_review: AIReviewOptions | None = None,
    style_options: RuntimeOptions | None = None,
    entrypoint_files: tuple[str, ...] = (),
    long_interview_screens: int = 10,
    github: bool = False,
    github_repository: str | None = None,
    github_ref: str | None = None,
) -> dict[str, Any]:
    """Inspect local question files and explicit review evidence without running interviews."""
    if long_interview_screens < 1:
        raise ValueError("long_interview_screens must be positive")
    style_options = style_options or RuntimeOptions(style_enabled=True, spellcheck=None)
    if research and not style_options.style_include_llm:
        style_options = replace(
            style_options,
            style_include_llm=True,
            style_vocabulary_only=True,
            style_openai_model=research.model,
            style_openai_base_url=research.base_url,
            style_openai_api_key=research.api_key,
        )
    root = root.resolve()
    evidence = evidence or {}
    files = question_files(root)
    # Bind human reviews to the package contents, including templates and tests.
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(
            part.startswith(".") for part in path.relative_to(root).parts
        ):
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.name == "publication-evidence.json":
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    revision = digest.hexdigest()
    evidence_current = evidence.get("source_sha256") == revision
    findings = []
    parsed = {}
    entrypoints = []
    checks: list[dict[str, Any]] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        docs, _ = parse_interview_documents(source, str(path))
        parsed[path] = docs
        findings.extend(
            find_errors_from_string(
                source,
                input_file=str(path),
                runtime_options=style_options,
            )
        )
        metadata = _find_metadata(docs)
        if metadata.get("title"):
            entrypoints.append(str(path.relative_to(root)))
            missing = [
                key
                for key in (
                    "title",
                    "short title",
                    "description",
                    "authors",
                    "jurisdiction",
                    "can_I_use_this_form",
                    "before_you_start",
                )
                if not metadata.get(key)
            ]
            if not (metadata.get("LIST_topics") or metadata.get("tags")):
                missing.append("LIST_topics or tags")
            checks.append(
                {
                    "id": "metadata",
                    "file": str(path.relative_to(root)),
                    "status": "needs_review" if missing else "pass",
                    "missing": missing,
                    "source": CHECKLIST_URL,
                }
            )
    scope = local_scope(root, parsed, entrypoint_files)
    active = {str(root / p) for p in scope["active_local_files"]}
    # Unselected source remains in raw findings but cannot block selected publication.
    checks = [c for c in checks if str(root / c["file"]) in active]
    # Style/translatability conventions are not automatically publication blockers.
    uncertain_guards = [f for f in findings if _has_local_default(f, parsed)]
    errors = [
        f
        for f in findings
        if f.file_name in active
        and f.severity == Severity.ERROR
        and f.finding_class not in {FindingClass.STYLE, FindingClass.TRANSLATABILITY}
        and f not in uncertain_guards
    ]
    design_errors = []
    for finding in findings:
        if (
            finding.file_name not in active
            or finding.message_id != MessageId.STYLE_MISSING_SCREEN_TITLE
        ):
            continue
        block_index = finding.context.get("repair_context", {}).get("block_index")
        docs = parsed.get(Path(finding.file_name or ""), [])
        matching = [d for d in docs if d.index == block_index]
        # A heading omitted for layout is not proof that the screen lacks a prompt.
        if matching and not any(
            matching[0].doc.get(k) for k in ("subquestion", "under", "note", "html")
        ):
            design_errors.append(finding)
    checks.append(
        check_result(
            "question_design",
            "blocked" if design_errors else "pass",
            "Missing question prompts without supplemental screen context are blockers; heading layout, sentence-length and vocabulary heuristics remain advisory.",
            findings=[
                {
                    "code": f.code,
                    "file": f.file_name,
                    "line": f.line_number,
                    "message": f.message,
                }
                for f in design_errors
            ],
        )
    )
    checks.extend(
        static_checks(
            root,
            {p: ds for p, ds in parsed.items() if str(p) in active},
            long_interview_screens=long_interview_screens,
            scope=scope,
        )
    )
    checks.append(
        check_result(
            "live_testing",
            "not_applicable",
            "Live interview/server/browser testing is outside this tool and is not a release gate.",
        )
    )
    if github:
        checks.append(
            github_publication(root, repository=github_repository, ref=github_ref)
        )
    else:
        checks.append(
            check_result(
                "github_publication",
                "not_checked",
                "Use --readiness-github to verify publication; local analysis does not imply code has been pushed.",
            )
        )
    checks.extend(
        [
            {
                "id": "question_files",
                "status": "pass" if files else "blocked",
                "count": len(files),
            },
            {
                "id": "entrypoint_metadata",
                "status": "pass" if entrypoints else "needs_review",
                "files": entrypoints,
            },
            {
                "id": "static_validation",
                "status": "blocked" if errors else "pass",
                "errors": len(errors),
            },
        ]
    )
    for key, (level, description) in REVIEWS.items():
        review = evidence.get(key)
        valid = (
            evidence_current
            and isinstance(review, dict)
            and review.get("passed") is True
            and all(
                isinstance(review.get(k), str) and review[k].strip()
                for k in ("reviewer", "date", "evidence")
            )
        )
        checks.append(
            {
                "id": key,
                "description": description,
                "status": "pass" if valid else "needs_review",
                "maturity_level": level,
                "source": MATURITY_URL,
                "evidence": review if isinstance(review, dict) else None,
                "severity": "info" if valid else "warning",
                "release_gate": True,
            }
        )
    research_report = None
    if research is not None:
        research_report = research_readiness(
            root, replace(research, entrypoint_files=entrypoint_files)
        )
        checks.append(
            {
                "id": "instructions_research",
                "status": research_report["status"],
                "execution_status": research_report["execution_status"],
                "model": research_report["model"],
            }
        )
    for check in checks:
        for key, value in check_policy(check["status"]).items():
            check.setdefault(key, value)
    status = (
        "blocked"
        if any(c["status"] == "blocked" for c in checks)
        else (
            "needs_review"
            if any(c["status"] == "needs_review" for c in checks)
            else "pass"
        )
    )

    def finding_record(f):
        release_gate = f in errors or f in design_errors
        severity = (
            "error"
            if release_gate
            else "warning" if f.severity == Severity.ERROR else str(f.severity)
        )
        uncertain_guard = f in uncertain_guards
        return dict(
            asdict(f),
            code=f.code,
            severity=severity,
            checker_severity=str(f.severity),
            message=(
                f"Check the default and display conditions for {f.context.get('field_name')!r}. This block assigns the field, so the guard check does not prove the interview will get stuck."
                if uncertain_guard
                else f.message
            ),
            readiness_evidence=(
                "default_assignment_needs_review" if uncertain_guard else "static_rule"
            ),
            release_gate=release_gate,
            readiness_severity=severity,
        )

    result = {
        "schema_version": 3,
        "policy": {
            "long_interview_screens": long_interview_screens,
            "live_testing_required": False,
            "template_conventions_block_release": False,
        },
        "research": research_report,
        "root": str(root),
        "status": status,
        "source_sha256": revision,
        "review_evidence_current": evidence_current,
        "scope": "Local publication pre-flight, not Court Forms Online acceptance or maturity certification",
        "maturity": {"assessed_level": None, "reference": MATURITY_URL},
        "checks": checks,
        "findings": [finding_record(f) for f in findings],
    }

    result["local_scope"] = scope
    result["review"] = review_view(result, scope)
    if ai_review is not None:
        result["ai_review"] = review_candidates(result, root, ai_review)
        apply_ai_review(result)
    return result


def _print_report(result, report_format):
    if report_format == "markdown":
        print(markdown_report(result), end="")
    else:
        print(json.dumps(result, indent=2, default=str))


def run_cli(
    root: Path,
    evidence_path: Path | None,
    parser: argparse.ArgumentParser,
    research: ResearchOptions | None = None,
    *,
    report_format: str = "json",
    ai_review: AIReviewOptions | None = None,
    long_interview_screens: int = 10,
    github: bool = False,
    github_repository: str | None = None,
    github_ref: str | None = None,
    playground: PlaygroundOptions | None = None,
    style_options: RuntimeOptions | None = None,
    entrypoint_files: tuple[str, ...] = (),
) -> int:
    """Shared CLI behavior for --readiness and the dedicated command."""
    if playground is not None:
        if entrypoint_files:
            parser.error(
                "Select Playground projects instead of local --readiness-entrypoint paths"
            )
        if evidence_path:
            parser.error(
                "Review evidence must be attached per snapshot; a single --evidence file cannot attest to multiple Playground projects"
            )
        try:
            result = scan_playgrounds(
                playground,
                research=research,
                style_options=style_options,
                long_interview_screens=long_interview_screens,
                **({"ai_review": ai_review} if ai_review is not None else {}),
            )
        except PlaygroundError as exc:
            _print_report(
                {
                    "status": "needs_review",
                    "source": "docassemble_playground",
                    "error": str(exc),
                },
                report_format,
            )
            return 2
        _print_report(result, report_format)
        return EXIT_CODES[result["status"]]
    if not root.is_dir():
        parser.error("readiness requires an existing repository directory")
    try:
        evidence = json.loads(evidence_path.read_text()) if evidence_path else None
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(f"cannot read review evidence: {exc}")
    if evidence is not None and not isinstance(evidence, dict):
        parser.error("evidence must be a JSON object")
    options: dict[str, Any] = {}
    if ai_review is not None:
        options["ai_review"] = ai_review
    if entrypoint_files:
        options["entrypoint_files"] = entrypoint_files
    if style_options and style_options != RuntimeOptions(
        style_enabled=True, spellcheck=None
    ):
        options["style_options"] = style_options
    if long_interview_screens != 10:
        options["long_interview_screens"] = long_interview_screens
    if github:
        options.update(
            github=True, github_repository=github_repository, github_ref=github_ref
        )
    if research is not None:
        print(f"Researching instructions with {research.model}...", file=sys.stderr)
        options["research"] = research
    try:
        result = publication_readiness(root, evidence=evidence, **options)
    except ValueError as exc:
        parser.error(str(exc))
    _print_report(result, report_format)
    return EXIT_CODES[result["status"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    parser.add_argument(
        "--evidence",
        type=Path,
        help="JSON review evidence (store outside the repo or as publication-evidence.json)",
    )
    add_research_arguments(parser)
    add_readiness_arguments(parser)
    parser.add_argument(
        "--openai-base-url", help="Responses-compatible endpoint (or OPENAI_BASE_URL)"
    )
    parser.add_argument(
        "--openai-api-key", help="Provider API key (prefer OPENAI_API_KEY)"
    )
    args = parser.parse_args(argv)
    return run_cli(
        args.root,
        args.evidence,
        parser,
        options_from_args(args, parser),
        **readiness_options_from_args(args, parser),
    )


if __name__ == "__main__":
    sys.exit(main())
