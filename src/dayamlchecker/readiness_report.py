"""Readable instructor reports from existing readiness evidence, without new AI calls."""

import html
import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

REVIEW_NAMES = {
    "legal_review": "Legal accuracy",
    "plain_language_review": "Clear questions and instructions",
    "interview_flow_review": "Interview flow and answer editing",
    "publication_review": "Final publication decision",
}


def source_findings(report, source):
    if source == "research":
        return (report.get("research") or {}).get("findings", [])
    return report.get("findings", [])


def _collapsed(summary, body):
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def _text(value):
    """Treat source text as text, not HTML or Markdown instructions."""
    text = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_\[\]#])", r"\\\1", text)


def _quote(value):
    text = str(value)
    fence = "`" * max(
        3, 1 + max((len(m[0]) for m in re.finditer(r"`+", text)), default=0)
    )
    return f"{fence}text\n{text}\n{fence}"


def _links(urls):
    result = []
    for url in urls:
        try:
            parsed = urlsplit(str(url))
            valid = parsed.scheme in {"https", "http"} and parsed.netloc
        except ValueError:
            valid = False
        if valid:
            result.append(
                f"[Source {len(result) + 1}](<{quote(str(url), safe=':/?=&%+#@;,-._~')}>)"
            )
    return ", ".join(result)


def _details(report, item):
    """Follow review indexes back to the evidence; never ask a model to reconstruct it."""
    source = item.get("source")
    findings = source_findings(report, source)
    rows = []
    if item.get("ai_review_decision"):
        rows.append(
            "**AI second opinion:** "
            + _text(item["ai_review_decision"])
            + ". "
            + _text(item["ai_review_reason"])
        )
        rows.append("**Original finding:** " + _text(item["original_message"]))
        if item.get("ai_review_file"):
            rows.append("**Reviewer evidence file:** " + _text(item["ai_review_file"]))
        if item.get("ai_review_quote"):
            rows.append(
                "**Evidence cited by the reviewer:**\n\n"
                + _quote(item["ai_review_quote"])
            )
    if item.get("reason"):
        rows.append(_text(item["reason"]))
    for index in item.get("finding_indexes", []):
        if not isinstance(index, int) or not 0 <= index < len(findings):
            continue
        finding = findings[index]
        if source == "research":
            for key, label in (
                ("affected_users", "Who could be affected"),
                ("failure_example", "What could go wrong"),
                ("baseline_reason", "Compared with the original form"),
                ("source_explanation", "Why the research raised this"),
            ):
                if finding.get(key):
                    rows.append(f"**{label}:** {_text(finding[key])}")
            evidence = finding.get("local_quote")
            links = _links(finding.get("source_urls", []))
            if links:
                rows.append("**Sources consulted:** " + links)
        else:
            context = finding.get("context") or {}
            repair = context.get("repair_context") or {}
            evidence = context.get("snippet") or repair.get("evidence")
            if finding.get("code"):
                rows.append("**Check:** " + _text(finding["code"]))
            if repair.get("source_yaml"):
                rows.append(
                    _collapsed("Show the source block", _quote(repair["source_yaml"]))
                )
        if evidence:
            rows.append("**Text that raised the concern:**\n\n" + _quote(evidence))
    if item.get("evidence"):
        rows.append(
            _collapsed(
                "Show check details",
                _quote(json.dumps(item["evidence"], indent=2, default=str)),
            )
        )
    return "\n\n".join(rows)


def _section(report, title, items, *, checklist=False):
    if not items:
        return ""
    lines = [f"## {title}"]
    for index, item in enumerate(items, 1):
        message = item.get(
            "message", item.get("detail", item.get("id", "Review this item"))
        )
        if checklist:
            lines.append(f"- [ ] **{index}.** {_text(message)}")
        else:
            lines.append(f"### {index}. {_text(message)}")
        if item.get("source") == "research":
            lines.append(
                "**AI research suggestion — check before treating it as a required fix.**"
            )
        if item.get("file"):
            location = _text(item["file"])
            if item.get("line"):
                location += f", line {item['line']}"
            lines.append("**Where to look:** " + location)
        detail = _details(report, item)
        if detail:
            lines.append(detail)
    return "\n\n".join(lines)


def markdown_report(report):
    """Render a readiness report. A quiet scan is never called publication approval."""
    if report.get("source") == "docassemble_playground":
        lines = [
            "# Playground publication review",
            "These are downloaded project files; GitHub publication has not been verified.",
        ]
        if report.get("error"):
            lines.append("**The scan could not finish:** " + _text(report["error"]))
        for project in report.get("projects", []):
            lines.append("# Project: " + _text(project["project"]))
            if project.get("report"):
                lines.append(markdown_report(project["report"]))
            else:
                lines.append(
                    _text(
                        project.get("error")
                        or project.get("detail")
                        or "No report available."
                    )
                )
        return "\n\n".join(lines) + "\n"

    review = report.get("review", {})
    actionable = review.get("actionable", [])
    blockers = [i for i in actionable if i.get("release_gate")]
    candidates = [i for i in actionable if not i.get("release_gate")]
    if blockers or report.get("status") == "blocked":
        assessment = "Automated checks found problems to address before publication."
    elif candidates:
        assessment = "Check the findings below before deciding whether to publish."
    else:
        assessment = "No automated publication blocker was found. Instructor review is still needed."
    lines = [
        "# Publication review: " + _text(Path(report.get("root", "interview")).name),
        "**Assessment:** " + assessment,
        "The aim is a useful tool compared with the original PDF, without clear added errors. Optional polish is listed separately. This report is generated from checker results; it is not an instructor’s approval or a live interview test.",
        "**Files reviewed:** " + _text(report.get("root", "Not recorded")),
    ]
    if report.get("source_sha256"):
        lines.append(
            "**Version fingerprint:** "
            + _text(report["source_sha256"])
            + ". Later file changes need a new review."
        )
    research = report.get("research")
    if research is None:
        lines.append(
            "**Legal/instruction research was not run.** Use `--readiness-research` to add source-based AI research. Static checks alone do not establish legal accuracy."
        )
    else:
        if research.get("checked_at"):
            lines.append("**Research date:** " + _text(research["checked_at"]))
        execution = research.get("execution_status", "unknown")
        lines.append(
            f"**AI research:** {_text(execution)}. Model: {_text(research.get('model', 'not recorded'))}. A completed research run is not proof that every problem was found."
        )
        if execution != "completed":
            lines.append(
                "**Research did not establish complete coverage.** Read the limits below; a failed or partial run is not a clean result."
            )
    ai_review = report.get("ai_review")
    if ai_review:
        state = ai_review.get("execution_status", "failed")
        lines.append(
            "**Optional AI second opinion:** "
            + _text(state)
            + ". Model: "
            + _text(ai_review.get("model", "unknown"))
            + ". This is not a human review; original findings and release status are preserved."
        )
        if ai_review.get("error"):
            lines.append(
                "**The second opinion could not finish:** " + _text(ai_review["error"])
            )
        for gap in ai_review.get("coverage_gaps", []):
            lines.append("- AI review limit: " + _text(gap))
        dismissed = review.get("ai_dismissed", [])
        if dismissed:
            lines.append(
                "**Findings set aside by AI:** "
                + str(len(dismissed))
                + ". Check its explanations below before accepting those decisions."
            )
    lines.append(
        _section(report, "Fix the automated blockers", blockers, checklist=True)
    )
    lines.append(
        _section(report, "Check these possible problems", candidates, checklist=True)
    )
    cleanup = review.get("cleanup", [])
    if cleanup:
        lines.append(
            _collapsed(
                "Optional improvements — not publication requirements",
                _section(report, "Optional improvements", cleanup),
            )
        )
    if review.get("ai_dismissed"):
        lines.append(
            _collapsed(
                "Findings the AI reviewer set aside — original evidence retained",
                _section(report, "Review these decisions", review["ai_dismissed"]),
            )
        )
    lines.append("## What this review could not establish")
    scope = report.get("local_scope") or {}
    for entrypoint in scope.get("entrypoints", []):
        if entrypoint.get("unresolved_includes"):
            lines.append(
                "- Some included libraries were not inspected for "
                + _text(entrypoint["file"])
                + ": "
                + _text(", ".join(entrypoint["unresolved_includes"]))
                + "."
            )

    coverage = review.get("coverage", [])
    for item in coverage:
        lines.append(
            "- "
            + _text(
                item.get("message")
                or item.get("detail")
                or f"{item.get('id', 'Check')}: {item.get('status', 'needs review')}"
            )
        )
    if research:
        if research.get("error"):
            lines.append("**Research error:** " + _text(research["error"]))
        for gap in research.get("coverage_gaps", []):
            lines.append("- " + _text(gap))
        for document in research.get("document_reviews", []):
            if document.get("status") in {"partial", "not_reviewed"}:
                lines.append(
                    "- "
                    + _text(
                        f"{document.get('document_id')}: {document.get('explanation', document.get('status'))}"
                    )
                )
        if research.get("unverified_claims"):
            lines.append(
                _collapsed(
                    "Optional claims to find sources for — not errors",
                    _quote(json.dumps(research["unverified_claims"], indent=2)),
                )
            )
    for check in report.get("checks", []):
        if check["id"] == "github_publication":
            lines.append(
                "**GitHub publication:** "
                + _text(check.get("detail") or check["status"])
                + " ("
                + _text(check["status"].replace("_", " "))
                + ")."
            )
    lines.append(
        "Static inspection does not prove that every answer reaches the right PDF field or that every interview path works. Missing findings should not be read as a clean publication decision."
    )
    process = review.get("process_evidence", [])
    lines.append("## Instructor decision")
    if process:
        names = [REVIEW_NAMES.get(c["id"], c["id"]) for c in process]
        lines.append(
            "Review records are missing or out of date for: "
            + ", ".join(names)
            + ". These are missing sign-offs, not additional defects in the student’s work."
        )
    lines.append(
        "After checking the evidence, record **ready**, **ready after specific fixes**, or **needs further review**. A suggested fix can be rejected when the source shows it is not needed; explain why. Keep optional improvements separate from the publication decision."
    )
    return "\n\n".join(line for line in lines if line) + "\n"


def main(argv=None):
    """Reformat a saved report without repeating scans, research, or API calls."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("report", type=Path, help="Saved readiness JSON (schema 3)")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text())
        if not isinstance(report, dict) or not (
            report.get("source") == "docassemble_playground"
            or all(key in report for key in ("root", "checks", "findings", "review"))
        ):
            raise ValueError(
                "Expected a full readiness report, not a research-only result"
            )
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print(markdown_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
