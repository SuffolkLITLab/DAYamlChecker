"""Prioritized, lossless review view, separate from certification/coverage state."""

from pathlib import Path
from dayamlchecker.readiness_report import REVIEW_NAMES
from dayamlchecker.readiness_scope import template_exposure

# These rules alone establish a convention, not a harmful user outcome.
CLEANUP_CODES = {
    "WS713",
    "WS714",
    "WS716",
    "WS717",
    "IS730",
    "WS726",
    "WS728",
    "IS712",
    "IS746",
    "WT701",
    "WT702",
    "WT703",
    "WT704",
    "WT705",
}
CONSEQUENCES = {
    "wrong_output",
    "blocked_user",
    "missed_deadline",
    "privacy_loss",
    "lost_benefits",
}


def review_view(report, scope):
    root = Path(report["root"])
    actionable, cleanup, coverage, process = [], [], [], []
    for index, f in enumerate(report["findings"]):
        try:
            file = str(Path(f["file_name"]).relative_to(root))
        except (ValueError, TypeError):
            file = f.get("file_name") or ""
        item = {
            "source": "static",
            "finding_indexes": [index],
            "file": file,
            "line": f.get("line_number"),
            "message": f["message"],
            "priority": "high" if f.get("release_gate") else "medium",
            "evidence_status": "static_rule",
            "release_gate": f.get("release_gate", False),
        }
        if "llm_" in f["message_id"]:
            coverage.append(item)
            continue
        if file not in scope["active_local_files"]:
            item.update(
                priority="low", reason="Outside the selected local include graph."
            )
            cleanup.append(item)
        elif f["code"] in CLEANUP_CODES:
            item.update(
                priority="low",
                reason="Optional wording, layout, naming or translation cleanup.",
            )
            cleanup.append(item)
        else:
            actionable.append(item)
    for index, f in enumerate((report.get("research") or {}).get("findings", [])):
        exposure = template_exposure(scope, f["file"])
        has_failure_evidence = all(
            isinstance(f.get(k), str) and f[k].strip()
            for k in ("affected_users", "failure_example", "baseline_reason")
        )
        supported_priority = (
            f.get("consequence") in CONSEQUENCES and has_failure_evidence
        )
        item = {
            "source": "research",
            "finding_indexes": [index],
            "file": f["file"],
            "line": f.get("line_number"),
            "message": f["concern"],
            "priority": "high" if supported_priority else "medium",
            "evidence_status": "proposal_needs_review",
            "release_gate": False,
            "impact": f.get("impact", "unclassified"),
            "exposure": exposure,
        }
        if exposure == "not_in_local_bundles":
            item.update(
                priority="low",
                reason="Not in selected local download bundles. Check external or dynamic paths before treating this as a user risk.",
            )
            cleanup.append(item)
        elif (
            f["file"].lower().endswith((".yml", ".yaml"))
            and f["file"] not in scope["active_local_files"]
        ):
            item.update(
                priority="low", reason="Outside the selected local include graph."
            )
            cleanup.append(item)
        elif (
            f.get("impact") in {"improvement", "inherited_limitation"}
            and not has_failure_evidence
        ):
            item.update(
                priority="low",
                reason="Advisory improvement; no concrete failure example supplied.",
            )
            cleanup.append(item)
        else:
            actionable.append(item)
    for c in report["checks"]:
        if c["id"] in REVIEW_NAMES:
            if c["status"] != "pass":
                process.append(c)
        elif c["id"] in {"instructions_research", "github_publication"}:
            if c["status"] not in {"pass", "not_checked"}:
                coverage.append(c)
        elif c["status"] in {"blocked", "needs_review", "warning"} and c["id"] not in {
            "static_validation",
            "question_design",
        }:
            item = {
                "source": "check",
                "check_id": c["id"],
                "file": c.get("file"),
                "message": c.get("detail", "Check the missing publication metadata."),
                "priority": "high" if c["status"] == "blocked" else "medium",
                "release_gate": c.get("release_gate", False),
                "evidence": c,
            }
            (
                cleanup
                if not c.get("release_gate")
                and c["id"]
                in {"document_templates", "project_setup", "filenames", "metadata"}
                else actionable
            ).append(item)

    # Merge identical advice at the same source location; keep every raw index.
    def group(items):
        groups = {}
        for item in items:
            key = (item["source"], item.get("file"), item.get("line"), item["message"])
            if key not in groups:
                groups[key] = item.copy()
            else:
                groups[key].setdefault("finding_indexes", []).extend(
                    item.get("finding_indexes", [])
                )
        return sorted(
            groups.values(),
            key=lambda x: (
                {"high": 0, "medium": 1, "low": 2}[x["priority"]],
                x.get("file") or "",
                x.get("line") or 0,
            ),
        )

    return {
        "actionable": group(actionable),
        "cleanup": group(cleanup),
        "coverage": coverage,
        "process_evidence": process,
        "defect_status": (
            "blocked"
            if any(
                i.get("release_gate") and i["priority"] == "high" for i in actionable
            )
            else "review_candidates" if actionable else "no_detected_blocker"
        ),
        "note": "Raw findings and checks are retained. Priority is not legal approval; research findings remain proposals.",
    }
