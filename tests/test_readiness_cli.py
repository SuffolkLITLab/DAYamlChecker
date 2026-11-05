import json

import pytest

from dayamlchecker import readiness
from dayamlchecker.yaml_structure import main


def test_readiness_flag_defaults_to_cwd_and_matches_separate_command(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert main(["--readiness"]) == 1
    combined = json.loads(capsys.readouterr().out)
    assert readiness.main([]) == 1
    assert json.loads(capsys.readouterr().out) == combined
    assert combined["status"] == "blocked"
    assert combined["root"] == str(tmp_path)


@pytest.mark.parametrize(
    "status,exit_code", [("pass", 0), ("blocked", 1), ("needs_review", 2)]
)
def test_readiness_forwards_evidence_and_status(
    tmp_path, monkeypatch, capsys, status, exit_code
):
    evidence_path = tmp_path / "evidence.json"
    evidence = {"source_sha256": "example"}
    evidence_path.write_text(json.dumps(evidence))

    def check(root, *, evidence):
        assert root == tmp_path
        assert evidence == {"source_sha256": "example"}
        return {"status": status}

    monkeypatch.setattr(readiness, "publication_readiness", check)
    assert (
        main([str(tmp_path), "--readiness", "--readiness-evidence", str(evidence_path)])
        == exit_code
    )
    assert json.loads(capsys.readouterr().out)["status"] == status


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--evidence", "review.json"],
        ["--readiness", "--fix"],
        ["--readiness", ".", "."],
        ["--readiness", "--format", "github"],
    ],
)
def test_invalid_cli_combinations(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_invalid_readiness_evidence_is_a_cli_error(tmp_path, capsys):
    path = tmp_path / "review.json"
    path.write_text("{broken")
    with pytest.raises(SystemExit) as exc:
        main(["--readiness", str(tmp_path), "--evidence", str(path)])
    assert exc.value.code == 2
    assert "cannot read review evidence" in capsys.readouterr().err


def test_readiness_honors_explicit_style_llm(tmp_path, monkeypatch, capsys):
    def check(root, *, evidence, style_options):
        assert style_options.style_include_llm
        assert style_options.style_openai_model == "test-model"
        return {"status": "pass"}

    monkeypatch.setattr(readiness, "publication_readiness", check)
    assert (
        main(
            [
                "--readiness",
                str(tmp_path),
                "--style-llm",
                "--openai-model",
                "test-model",
            ]
        )
        == 0
    )
