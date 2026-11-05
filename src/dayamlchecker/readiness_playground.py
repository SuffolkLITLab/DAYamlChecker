"""Read-only snapshots of a docassemble user's unpublished Playground projects."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any
from urllib.parse import urlsplit

import requests


@dataclass(frozen=True)
class PlaygroundOptions:
    server: str
    user: str | None = None
    projects: tuple[str, ...] = ()
    api_key: str | None = field(default=None, repr=False)


class PlaygroundError(ValueError):
    pass


class PlaygroundReader:
    def __init__(self, options: PlaygroundOptions):
        parsed = urlsplit(options.server)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise PlaygroundError(
                "Use a server base URL without credentials, query, or fragment."
            )
        if parsed.scheme == "http" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise PlaygroundError(
                "Use HTTPS except for a localhost development server."
            )
        self.base = options.server.rstrip("/")
        self.key = options.api_key or os.getenv("DOCASSEMBLE_API_KEY", "")
        if not self.key:
            raise PlaygroundError(
                "Set DOCASSEMBLE_API_KEY to a key permitted to read this user's Playground."
            )
        self.options = options
        self.total_bytes = 0

    def get(self, endpoint: str, **params: Any) -> requests.Response:
        try:
            response = requests.get(
                self.base + endpoint,
                headers={"X-API-Key": self.key},
                params=params,
                timeout=30,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise PlaygroundError("Docassemble request failed.") from None
        if response.status_code != 200:
            raise PlaygroundError(
                f"Docassemble {endpoint} returned HTTP {response.status_code}; verify server URL, user, project and read permissions."
            )
        self.total_bytes += len(response.content)
        if len(response.content) > 20_000_000 or self.total_bytes > 100_000_000:
            raise PlaygroundError("Playground snapshot exceeds download size limit.")
        return response

    def json(self, endpoint: str, **params: Any):
        response = self.get(endpoint, **params)
        try:
            return response.json()
        except (ValueError, TypeError):
            raise PlaygroundError("Docassemble returned invalid JSON.") from None

    def user_id(self) -> int:
        user = self.options.user
        if user and user.isdigit():
            return int(user)
        info = (
            self.json("/api/user_info", username=user)
            if user
            else self.json("/api/user")
        )
        if not isinstance(info, dict) or not isinstance(info.get("id"), int):
            raise PlaygroundError("Could not resolve the requested user's ID.")
        return info["id"]

    def projects(self, user_id: int) -> list[str]:
        projects = self.json("/api/playground/project", user_id=user_id)
        if not isinstance(projects, list) or not all(
            isinstance(p, str) for p in projects
        ):
            raise PlaygroundError("Invalid Playground project listing.")
        available = list(dict.fromkeys(["default", *projects]))
        selected = list(self.options.projects) or available
        if any(project not in available for project in selected):
            raise PlaygroundError("A requested Playground project does not exist.")
        if len(selected) > 100:
            raise PlaygroundError(
                "Select fewer projects with --playground-project (maximum 100)."
            )
        return selected

    def snapshot(self, root: Path, user_id: int, project: str) -> list[dict]:
        manifest = []
        for folder in ("questions", "templates", "modules", "static", "sources"):
            names = self.json(
                "/api/playground", user_id=user_id, project=project, folder=folder
            )
            if not isinstance(names, list) or not all(
                isinstance(n, str) for n in names
            ):
                raise PlaygroundError("Invalid Playground file listing.")
            if len(names) > 1000:
                raise PlaygroundError("Playground folder exceeds the file-count limit.")
            for name in names:
                relative = PurePosixPath(name)
                if name.startswith(".") and ".." not in relative.parts:
                    continue
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in name
                    or ":" in name
                    or not name
                    or name.startswith(".")
                ):
                    raise PlaygroundError("Unsafe path in Playground file listing.")
                package = root / "docassemble" / "PlaygroundSnapshot"
                destination = (
                    package / name
                    if folder == "modules"
                    else package / "data" / folder / name
                )
                content = self.get(
                    "/api/playground",
                    user_id=user_id,
                    project=project,
                    folder=folder,
                    filename=name,
                ).content
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                manifest.append(
                    {
                        "folder": folder,
                        "filename": name,
                        "snapshot_path": str(destination.relative_to(root)),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
        return manifest


def scan_playgrounds(
    options: PlaygroundOptions,
    *,
    research=None,
    style_options=None,
    ai_review=None,
    long_interview_screens: int = 10,
) -> dict:
    from dayamlchecker.readiness import publication_readiness

    reader = PlaygroundReader(options)
    user_id = reader.user_id()
    reports: list[dict[str, Any]] = []
    for project in reader.projects(user_id):
        try:
            with tempfile.TemporaryDirectory(
                prefix="dayamlchecker-playground-"
            ) as temporary:
                root = Path(temporary)
                manifest = reader.snapshot(root, user_id, project)
                if not any(
                    item["folder"] == "questions"
                    and item["filename"].endswith((".yml", ".yaml"))
                    for item in manifest
                ):
                    reports.append(
                        {
                            "project": project,
                            "status": "not_applicable",
                            "detail": "No question YAML in this project.",
                            "files": manifest,
                        }
                    )
                    continue
                report = publication_readiness(
                    root,
                    research=research,
                    long_interview_screens=long_interview_screens,
                    style_options=style_options,
                    **({"ai_review": ai_review} if ai_review is not None else {}),
                )

                # Snapshot paths are temporary. Preserve original project/file identity.
                def relocate(value):
                    if isinstance(value, str):
                        return value.replace(str(root), "playground:" + project)
                    if isinstance(value, list):
                        return [relocate(v) for v in value]
                    if isinstance(value, dict):
                        return {k: relocate(v) for k, v in value.items()}
                    return value

                reports.append(
                    {"project": project, "files": manifest, "report": relocate(report)}
                )
        except (PlaygroundError, OSError, UnicodeError) as exc:
            reports.append(
                {"project": project, "status": "needs_review", "error": str(exc)}
            )
    statuses = [p.get("report", p).get("status", "needs_review") for p in reports]
    status = (
        "blocked"
        if "blocked" in statuses
        else (
            "needs_review"
            if "needs_review" in statuses
            or not reports
            or all(s == "not_applicable" for s in statuses)
            else "pass"
        )
    )
    return {
        "schema_version": 1,
        "source": "docassemble_playground",
        "server": reader.base,
        "user_id": user_id,
        "status": status,
        "projects": reports,
        "scope": "Read-only source snapshots; no interviews executed, files uploaded, or GitHub publication assumed.",
    }
