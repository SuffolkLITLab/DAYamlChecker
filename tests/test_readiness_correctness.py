"""Regression tests for findings that must not be hidden or misreported."""

from pathlib import Path

import pytest

from dayamlchecker import readiness_ai_review as ai
from dayamlchecker import readiness_research as research
from dayamlchecker import RuntimeOptions, find_style_findings_from_string, style
from dayamlchecker.messages import Severity
from dayamlchecker.readiness import publication_readiness
from dayamlchecker.readiness_review import review_view
from dayamlchecker.readiness_scope import local_scope, template_exposure
from dayamlchecker.yaml_structure import main, parse_interview_documents

TITLE = "metadata:\n  title: Main\n---\n"
PREFIX = "docassemble/demo/data/"
BROKEN_CODE = "code: |\n  def broken(:\n    pass\n"


def write(root, name, text):
    p = root / PREFIX / "questions" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def check(report, check_id):
    return next(c for c in report["checks"] if c["id"] == check_id)


def scope_of(root, *paths):
    parsed = {p: parse_interview_documents(p.read_text(), str(p))[0] for p in paths}
    return local_scope(root, parsed)


@pytest.mark.parametrize(
    "reference",
    [
        "docassemble.demo:data/questions/lib.yml",
        "docassemble.demo:lib.yml",
        "lib.yml",
    ],
)
def test_package_includes_keep_included_errors_in_scope(tmp_path, reference):
    write(tmp_path, "main.yml", f"{TITLE}include:\n  - {reference}\n")
    write(tmp_path, "lib.yml", BROKEN_CODE)
    report = publication_readiness(tmp_path)
    assert PREFIX + "questions/lib.yml" in report["local_scope"]["active_local_files"]
    assert not report["local_scope"]["entrypoints"][0]["unresolved_includes"]
    assert check(report, "static_validation")["status"] == "blocked"


def test_relative_include_falls_back_to_package_questions_folder(tmp_path):
    main_file = write(tmp_path, "nested/main.yml", f"{TITLE}include:\n  - lib.yml\n")
    lib = write(tmp_path, "lib.yml", "id: lib\nquestion: Library\nfield: answer\n")
    scope = scope_of(tmp_path, main_file, lib)
    assert PREFIX + "questions/lib.yml" in scope["active_local_files"]


def test_unparseable_file_blocks_inferred_scope_only(tmp_path):
    write(tmp_path, "good.yml", f"{TITLE}id: a\nquestion: Good\nfield: answer\n")
    write(tmp_path, "broken.yml", "metadata: {title: Broken\n")
    report = publication_readiness(tmp_path)
    assert check(report, "static_validation")["status"] == "blocked"
    selected = publication_readiness(
        tmp_path, entrypoint_files=(PREFIX + "questions/good.yml",)
    )
    assert check(selected, "static_validation")["status"] == "pass"


def test_missing_question_attachment_blocks_despite_unrelated_bundle(tmp_path):
    write(
        tmp_path,
        "main.yml",
        TITLE + """objects:
  - other: ALDocumentBundle.using(elements=[])
---
id: start
question: Start
subquestion: ${ other.download_list_html() }
continue button field: started
---
id: done
question: Your form
attachment:
  variable name: direct_doc
  docx template file: missing_direct.docx
""",
    )
    delivery = check(publication_readiness(tmp_path), "document_delivery")
    assert [e["reference"] for e in delivery["errors"]] == ["missing_direct.docx"]


@pytest.mark.parametrize(
    "use",
    ["form.pdf.url_for()", "form.as_editable_list()", "form[0].as_pdf()"],
)
def test_direct_attachment_uses_count_as_delivery(tmp_path, use):
    p = write(
        tmp_path,
        "main.yml",
        TITLE + f"""id: done
event: done
question: Done
subquestion: ${{ {use} }}
---
attachments:
  - name: Form
    variable name: form[i]
    docx template file: form.docx
""",
    )
    exposure = template_exposure(scope_of(tmp_path, p), PREFIX + "templates/form.docx")
    assert exposure == "potentially_delivered"


def test_template_filename_is_not_mistaken_for_delivery(tmp_path):
    p = write(
        tmp_path,
        "main.yml",
        TITLE + """attachments:
  - name: Form
    variable name: form
    docx template file: form.docx
""",
    )
    exposure = template_exposure(scope_of(tmp_path, p), PREFIX + "templates/form.docx")
    assert exposure == "unknown"


def test_llm_quote_of_normalized_text_keeps_finding():
    source = """id: start
question: Start
subquestion: |
  You must explain the
  [form](https://example.org) today.
field: answer
"""
    docs, _ = parse_interview_documents(source, "main.yml")

    def build(quote):
        return style._build_llm_finding(
            parsed_docs=docs,
            input_file="main.yml",
            rule_id="tone-and-respect",
            message="Soften this.",
            problematic_text=quote,
            screen_id="start",
        )

    assert build("You must explain the form today.") is not None
    assert build("This sentence is not on the screen.") is None
    assert build("${ value }") is None


def test_gating_metadata_is_not_reported_as_optional(tmp_path):
    write(tmp_path, "main.yml", f"{TITLE}id: a\nquestion: Good\nfield: answer\n")
    review = publication_readiness(tmp_path)["review"]
    assert [i["check_id"] for i in review["actionable"]].count("metadata") == 1
    assert not [i for i in review["cleanup"] if i.get("check_id") == "metadata"]
    assert review["defect_status"] != "no_detected_blocker"


def test_research_on_unselected_question_file_is_cleanup():
    report = {
        "root": "/repo",
        "findings": [],
        "checks": [],
        "research": {
            "findings": [{"file": "other.yml", "concern": "Check this", "impact": "x"}]
        },
    }
    view = review_view(report, {"active_local_files": ["main.yml"], "templates": {}})
    assert not view["actionable"]
    assert view["cleanup"][0]["reason"] == "Outside the selected local include graph."


def test_ai_context_only_includes_reviewed_candidates(monkeypatch):
    monkeypatch.setattr(
        ai,
        "collect_material",
        lambda *a: {"documents": [], "coverage_gaps": []},
    )
    findings = [
        {"code": "IS1", "context": {"repair_context": {"source_yaml": block}}}
        for block in ("reviewed: block", "skipped: block")
    ]
    items = [
        {
            "source": "static",
            "file": "main.yml",
            "message": f"Finding {index}",
            "finding_indexes": [index],
        }
        for index in range(2)
    ]
    report = {
        "source_sha256": "revision",
        "findings": findings,
        "review": {"actionable": items, "cleanup": []},
    }
    material, _, _ = ai.prepare_review(
        report, Path("/repo"), ai.AIReviewOptions(max_candidates=1)
    )
    assert [d["text"] for d in material["documents"]] == ["reviewed: block"]


def test_research_budget_prefers_selected_entrypoint(tmp_path):
    filler = "note: " + "x" * research.MAX_DOCUMENT_CHARS + "\n"
    for index in range(research.MAX_INPUT_CHARS // research.MAX_DOCUMENT_CHARS + 1):
        write(tmp_path, f"a{index}.yml", filler)
    selected = PREFIX + "questions/z_main.yml"
    write(tmp_path, "z_main.yml", f"{TITLE}id: a\nquestion: Main\nfield: answer\n")
    material = research.collect_material(
        tmp_path, research.ResearchOptions(entrypoint_files=(selected,))
    )
    assert material["documents"][0]["file"] == selected


def test_capitalized_replacement_at_sentence_start_is_valid():
    before = "Provide your name to the court clerk today."
    decision = {
        "candidate_id": "1",
        "decision": "keep",
        "confidence": "high",
        "reason": "Clearer.",
        "evidence": before,
        "replacement": "give",
        "original_sentence": before,
        "revised_sentence": "Give your name to the court clerk today.",
    }
    candidate = {"candidate_id": "1", "term": "provide", "text": before}
    result = style._validated_vocabulary_decisions(
        {"decisions": [decision]}, [candidate]
    )
    assert result["1"]["decision"] == "keep"


def test_review_digest_ignores_reports_and_build_output(tmp_path):
    p = write(tmp_path, "main.yml", f"{TITLE}id: a\nquestion: Good\nfield: answer\n")
    digest = publication_readiness(tmp_path)["source_sha256"]
    (tmp_path / "report.json").write_text("{}")
    (tmp_path / "venv/lib").mkdir(parents=True)
    (tmp_path / "venv/lib/module.py").write_text("x = 1\n")
    assert publication_readiness(tmp_path)["source_sha256"] == digest
    (tmp_path / "setup.py").write_text("setup()\n")
    with_setup = publication_readiness(tmp_path)["source_sha256"]
    assert with_setup != digest
    p.write_text(p.read_text() + "---\nid: b\nquestion: More\nfield: other\n")
    assert publication_readiness(tmp_path)["source_sha256"] != with_setup


def test_noyesmaybe_screens_count_toward_long_interview_gate(tmp_path):
    screens = "---\n".join(
        f"id: s{i}\nquestion: Screen {i}\nnoyesmaybe: answer_{i}\n" for i in range(2)
    )
    write(tmp_path, "main.yml", TITLE + screens)
    report = publication_readiness(tmp_path, long_interview_screens=2)
    assert check(report, "answer_review")["estimated_input_screens"] == 2


@pytest.mark.parametrize(
    "args",
    [
        ["--readiness-entrypoint", "main.yml"],
        ["--long-interview-screens", "5"],
        ["--readiness-review-model", "other"],
        ["--readiness-review-timeout", "5"],
        ["--readiness-review-max-candidates", "5"],
        ["--readiness-evidence", "evidence.json"],
    ],
)
def test_readiness_options_are_not_silently_ignored(args, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["example.yml", *args])
    assert exc.value.code == 2
    assert "require --readiness" in capsys.readouterr().err


def test_precision_reports_how_many_word_suggestions_it_hid():
    source = "id: start\nquestion: Please utilize the form\nfield: answer\n"
    options = RuntimeOptions(style_enabled=True)
    findings = find_style_findings_from_string(source, runtime_options=options)
    notices = [f for f in findings if f.code == "IS749"]
    assert len(notices) == 1
    assert notices[0].severity == Severity.INFO
    assert notices[0].context["hidden_count"] >= 2
    assert "--style-review-level thorough" in notices[0].message
    thorough = find_style_findings_from_string(
        source,
        runtime_options=RuntimeOptions(
            style_enabled=True, style_review_level="thorough"
        ),
    )
    assert not [f for f in thorough if f.code == "IS749"]


def test_hidden_word_suggestion_notice_is_cleanup_in_readiness(tmp_path):
    write(
        tmp_path,
        "main.yml",
        f"{TITLE}id: a\nquestion: Please utilize the form\nfield: answer\n",
    )
    report = publication_readiness(tmp_path)
    notice = [
        index for index, f in enumerate(report["findings"]) if f["code"] == "IS749"
    ]
    assert len(notice) == 1 and not report["findings"][notice[0]]["release_gate"]
    assert notice[0] not in [
        index
        for item in report["review"]["actionable"]
        for index in item.get("finding_indexes", [])
    ]
