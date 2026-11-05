import json
from pathlib import Path

import pytest

from dayamlchecker import readiness_github as github
from dayamlchecker import readiness_playground as playground
from dayamlchecker.yaml_structure import main


class Response:
    def __init__(self, data=None, content=None, status=200):
        self.data = data
        self.content = content if content is not None else json.dumps(data).encode()
        self.status_code = status

    def json(self):
        return self.data


@pytest.mark.parametrize(
    "dirty,remote_sha,expected",
    [
        ("", "abc", "pass"),
        (" M main.yml", "abc", "needs_review"),
        ("", "def", "needs_review"),
        (None, "abc", "needs_review"),
    ],
)
def test_github_checks_exact_commit_and_working_tree(
    tmp_path, monkeypatch, dirty, remote_sha, expected
):
    def git(root, *args):
        return {
            (
                "remote",
                "get-url",
                "origin",
            ): "git@github.com:owner/docassemble-Test.git",
            ("rev-parse", "HEAD"): "abc",
            ("symbolic-ref", "--short", "HEAD"): "main",
            ("status", "--porcelain"): dirty,
        }[args]

    monkeypatch.setattr(github, "_git", git)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        return Response(
            {"sha": remote_sha} if "/commits/" in url else {"default_branch": "main"}
        )

    monkeypatch.setattr(github.requests, "get", get)
    result = github.github_publication(tmp_path)
    assert result["status"] == expected
    assert result["naming_advisories"]
    assert len(calls) == 2


def fake_playground(monkeypatch, unsafe=False, forbidden=False):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs.get("params")))
        assert kwargs["headers"]["X-API-Key"] == "secret"
        assert kwargs["allow_redirects"] is False
        if forbidden:
            return Response(status=403)
        if url.endswith("/api/user_info"):
            assert kwargs["params"]["username"] == "author@example.org"
            return Response({"id": 7})
        if url.endswith("/api/user"):
            return Response({"id": 7})
        if url.endswith("/api/playground/project"):
            return Response(["Draft"])
        assert url.endswith("/api/playground")
        params = kwargs["params"]
        if params.get("filename"):
            return Response(
                content=b"id: start\nquestion: Your name\nfields:\n  - Name: user_name\n"
            )
        if params["project"] == "Draft" and params["folder"] == "questions":
            return Response(["../escape.yml"] if unsafe else ["main.yml"])
        return Response([])

    monkeypatch.setattr(playground.requests, "get", get)
    return calls


def test_playground_scans_unpublished_projects_read_only(monkeypatch):
    calls = fake_playground(monkeypatch)
    result = playground.scan_playgrounds(
        playground.PlaygroundOptions(
            "http://localhost", "author@example.org", api_key="secret"
        )
    )
    assert result["user_id"] == 7
    assert result["projects"][0]["status"] == "not_applicable"
    draft = result["projects"][1]
    assert draft["project"] == "Draft"
    assert draft["files"][0]["filename"] == "main.yml"
    assert draft["report"]["root"] == "playground:Draft"
    assert "secret" not in json.dumps(result)
    assert all("/api/playground" in url or "/api/user_info" in url for url, _ in calls)


def test_playground_rejects_traversal_without_writing(monkeypatch):
    fake_playground(monkeypatch, unsafe=True)
    result = playground.scan_playgrounds(
        playground.PlaygroundOptions(
            "http://localhost", projects=("Draft",), api_key="secret"
        )
    )
    assert result["status"] == "needs_review"
    assert "Unsafe path" in result["projects"][0]["error"]


def test_playground_permissions_are_reported_without_leaking_key(monkeypatch):
    fake_playground(monkeypatch, forbidden=True)
    with pytest.raises(playground.PlaygroundError, match="HTTP 403"):
        playground.scan_playgrounds(
            playground.PlaygroundOptions("http://localhost", api_key="secret")
        )


def test_cli_playground_requires_no_local_directory(monkeypatch, capsys):
    fake_playground(monkeypatch)
    monkeypatch.setenv("DOCASSEMBLE_API_KEY", "secret")
    assert (
        main(
            [
                "--readiness",
                "--playground-server",
                "http://localhost",
                "--playground-user",
                "author@example.org",
                "--playground-project",
                "Draft",
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert result["source"] == "docassemble_playground"
    assert len(result["projects"]) == 1


@pytest.mark.parametrize(
    "args",
    [
        ["--readiness", "--playground-server", "http://localhost", "."],
        ["--readiness", "--playground-user", "author@example.org"],
        ["--readiness", "--long-interview-screens", "0"],
        [
            "--readiness",
            "--playground-server",
            "http://localhost",
            "--readiness-github",
        ],
    ],
)
def test_invalid_readiness_source_combinations(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
