"""Read-only GitHub publication checks for the exact local checkout."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

import requests

from dayamlchecker.readiness_static import check_result, naming_issues


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def github_publication(
    root: Path, *, repository: str | None = None, ref: str | None = None
) -> dict:
    remote = _git(root, "remote", "get-url", "origin") or ""
    if repository is None:
        match = re.fullmatch(
            r"(?:git@github\.com:|https://github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?/?",
            remote,
        )
        repository = match[1] if match else None
    if not repository or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        return check_result(
            "github_publication",
            "needs_review",
            "No GitHub owner/repository could be determined. Use --github-repository.",
        )
    issues = naming_issues(repository.split("/")[1], repository=True)
    head = _git(root, "rev-parse", "HEAD")
    branch = ref or _git(root, "symbolic-ref", "--short", "HEAD")
    dirty = _git(root, "status", "--porcelain")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    base = "https://api.github.com/repos/" + repository
    try:
        response = requests.get(
            base, headers=headers, timeout=20, allow_redirects=False
        )
        if response.status_code != 200:
            return check_result(
                "github_publication",
                "needs_review",
                f"GitHub repository lookup returned HTTP {response.status_code}; unavailable/private/renamed repositories and missing credentials are not proof of publication.",
                repository=repository,
                naming_advisories=issues,
            )
        info = response.json()
        branch = branch or info["default_branch"]
        response = requests.get(
            base + "/commits/" + quote(branch, safe=""),
            headers=headers,
            timeout=20,
            allow_redirects=False,
        )
        if response.status_code != 200:
            return check_result(
                "github_publication",
                "needs_review",
                f"Published ref could not be read (HTTP {response.status_code}).",
                repository=repository,
                ref=branch,
                naming_advisories=issues,
            )
        remote_sha = response.json()["sha"]
        current = bool(head) and head == remote_sha and dirty == ""
        archived = bool(info.get("archived") or info.get("disabled"))
        return check_result(
            "github_publication",
            "pass" if current and not archived else "needs_review",
            "Compared local HEAD and working tree with the GitHub ref. No code was pushed. CI and release approval are outside this check.",
            repository=repository,
            url=f"https://github.com/{repository}",
            ref=branch,
            local_commit=head or None,
            remote_commit=remote_sha,
            local_changes=bool(dirty) if dirty is not None else None,
            contents_match=current,
            archived_or_disabled=archived,
            private=info.get("private"),
            naming_advisories=issues,
            naming_severity="warning" if issues else "info",
        )
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return check_result(
            "github_publication",
            "needs_review",
            "GitHub could not be checked; no successful publication verification is available.",
            repository=repository,
            naming_advisories=issues,
        )
