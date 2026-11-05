from pathlib import Path
from dayamlchecker.readiness import publication_readiness
from dayamlchecker.readiness_scope import local_scope, template_exposure
from dayamlchecker.yaml_structure import parse_interview_documents
from dayamlchecker import style


def write(root, name, text):
    p = root / "docassemble/demo/data/questions" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_external_library_questions_do_not_inflate_launcher(tmp_path):
    write(
        tmp_path,
        "main.yml",
        "metadata:\n  title: Resume\n---\ninclude:\n  - docassemble.Library:many_questions.yml\n---\nmandatory: True\nquestion: Resume a saved session\nevent: resume\n",
    )
    # A sibling library is deliberately available to the older include resolver.
    lib = (
        tmp_path.parent
        / "docassemble-Library/docassemble/Library/data/questions/many_questions.yml"
    )
    lib.parent.mkdir(parents=True, exist_ok=True)
    lib.write_text(
        "---\n".join(f"question: Detail {i}\nfield: detail_{i}\n" for i in range(20))
    )
    report = publication_readiness(tmp_path)
    c = next(c for c in report["checks"] if c["id"] == "answer_review")
    assert c["estimated_input_screens"] == 0
    assert c["status"] == "pass"


def test_local_includes_still_count_and_missing_template_still_blocks(tmp_path):
    write(
        tmp_path, "main.yml", "metadata:\n  title: Main\n---\ninclude:\n  - body.yml\n"
    )
    write(
        tmp_path,
        "body.yml",
        "---\n".join(f"question: Detail {i}\nfield: detail_{i}\n" for i in range(12))
        + "---\nattachment:\n  name: Form\n  pdf template file: absent.pdf\n",
    )
    r = publication_readiness(tmp_path)
    assert (
        next(c for c in r["checks"] if c["id"] == "answer_review")[
            "estimated_input_screens"
        ]
        == 12
    )
    assert any(
        c["id"] == "document_delivery" and c["status"] == "blocked" for c in r["checks"]
    )


def test_explicit_entrypoint_does_not_block_on_unselected_interview(tmp_path):
    p = write(
        tmp_path,
        "main.yml",
        "metadata:\n  title: Main\n---\nid: name-question\nquestion: Name\nfield: user_name\n",
    )
    write(
        tmp_path,
        "draft.yml",
        "metadata:\n  title: Draft\n---\nattachment:\n  name: Draft\n  pdf template file: missing.pdf\n",
    )
    r = publication_readiness(
        tmp_path, entrypoint_files=(str(p.relative_to(tmp_path)),)
    )
    assert not any(c["status"] == "blocked" for c in r["checks"])
    assert r["local_scope"]["selection"] == "explicit"


def test_bundle_exposure_keeps_unknown_conditions_conservative(tmp_path):
    p = write(
        tmp_path,
        "main.yml",
        """metadata:
  title: Main
---
objects:
  - al_user_bundle: ALDocumentBundle.using(elements=[form])
---
event: download
question: Download
subquestion: ${ al_user_bundle.download_list_html() }
---
attachments:
  - name: Form
    variable name: form[i]
    docx template file: form.docx
  - name: Unused
    variable name: unused[i]
    docx template file: unused.docx
""",
    )
    docs, _ = parse_interview_documents(p.read_text(), str(p))
    scope = local_scope(tmp_path, {p: docs})
    prefix = "docassemble/demo/data/templates/"
    assert template_exposure(scope, prefix + "form.docx") == "potentially_delivered"
    assert template_exposure(scope, prefix + "unused.docx") == "not_in_local_bundles"
    p.write_text(p.read_text().replace("elements=[form]", "elements=make_documents()"))
    docs, _ = parse_interview_documents(p.read_text(), str(p))
    assert (
        template_exposure(local_scope(tmp_path, {p: docs}), prefix + "unused.docx")
        == "unknown"
    )


def test_cleanup_and_process_preserve_raw_findings(tmp_path):
    write(
        tmp_path,
        "main.yml",
        "metadata:\n  title: Main\n---\nid: name-question\nquestion: Name\nsubquestion: "
        + " ".join(["This"] * 25)
        + ".\nfield: user_name\n",
    )
    r = publication_readiness(tmp_path)
    assert any(f["code"] == "WS714" for f in r["findings"])
    assert any(i.get("finding_indexes") for i in r["review"]["cleanup"])
    assert len(r["review"]["process_evidence"]) == 4
    assert r["review"]["defect_status"] != "blocked"


def test_real_missing_guard_still_blocks_but_default_is_review_candidate(tmp_path):
    text = """metadata:
  title: Main
---
question: Eligibility
fields:
  - Eligible: eligible
    datatype: yesno
  - Detail: detail
    show if: eligible
---
id: interview order
code: |
  detail
"""
    p = write(tmp_path, "main.yml", text)
    r = publication_readiness(tmp_path)
    assert any(f["code"] == "EG308" and f["release_gate"] for f in r["findings"])
    p.write_text(
        text.replace("  detail\n", '  if not eligible:\n    detail = ""\n  detail\n')
    )
    r = publication_readiness(tmp_path)
    assert any(f["code"] == "EG308" and not f["release_gate"] for f in r["findings"])
    p.write_text(
        text.replace("  detail\n", '  detail\n  if not eligible:\n    detail = ""\n')
    )
    r = publication_readiness(tmp_path)
    assert any(f["code"] == "EG308" and f["release_gate"] for f in r["findings"])


def test_replacement_rejects_live_bad_edits_and_keeps_good_edit():
    for before, term, replacement, keep in [
        (
            "This is a mandatory chance to settle your case.",
            "mandatory",
            "you must",
            False,
        ),
        (
            "CLA is solely responsible for its content.",
            "solely",
            "the only one responsible",
            False,
        ),
        ("Explain room and/or board payments.", "and/or", "a or b or both", False),
        ("Please commence your application here.", "commence", "start", True),
    ]:
        c = {"candidate_id": "1", "term": term, "text": before}
        d = {
            "candidate_id": "1",
            "decision": "keep",
            "confidence": "high",
            "reason": "Clearer.",
            "evidence": before,
            "replacement": replacement,
            "original_sentence": before,
            "revised_sentence": before.replace(term, replacement),
        }
        result = style._validated_vocabulary_decisions({"decisions": [d]}, [c])["1"]
        assert (result["decision"] == "keep") == keep


def test_missing_inactive_bundle_template_is_cleanup_but_active_missing_blocks(
    tmp_path,
):
    p = write(
        tmp_path,
        "main.yml",
        """metadata:
  title: Main
---
objects:
  - al_user_bundle: ALDocumentBundle.using(elements=[form])
---
id: download
question: Download
subquestion: ${ al_user_bundle.download_list_html() }
event: download
---
attachments:
  - name: Form
    variable name: form[i]
    docx template file: form.docx
  - name: Unused
    variable name: unused[i]
    docx template file: unused.docx
""",
    )
    templates = p.parent.parent / "templates"
    templates.mkdir()
    (templates / "form.docx").write_bytes(b"not a docx")
    r = publication_readiness(tmp_path)
    delivery = next(c for c in r["checks"] if c["id"] == "document_delivery")
    assert delivery["status"] == "warning" and not delivery["errors"]
    (templates / "form.docx").unlink()
    r = publication_readiness(tmp_path)
    delivery = next(c for c in r["checks"] if c["id"] == "document_delivery")
    assert delivery["status"] == "blocked"
    assert [e["reference"] for e in delivery["errors"]] == ["form.docx"]


def test_concrete_failure_is_not_hidden_by_advisory_model_label(tmp_path):
    from dayamlchecker.readiness_review import review_view

    finding = {
        "file": "main.yml",
        "concern": "Filing court: check the destination.",
        "impact": "improvement",
        "consequence": "clarity",
        "affected_users": "People appealing from this court.",
        "failure_example": "A filer sends the motion to a court that cannot hear it.",
        "baseline_reason": "The interview chooses the destination.",
    }
    report = {
        "root": str(tmp_path),
        "findings": [],
        "checks": [],
        "research": {"findings": [finding]},
    }
    view = review_view(report, {"active_local_files": ["main.yml"]})
    assert view["actionable"][0]["priority"] == "medium"
    assert not view["actionable"][0]["release_gate"]
    assert not view["cleanup"]
    finding["failure_example"] = ""
    view = review_view(report, {"active_local_files": ["main.yml"]})
    assert not view["actionable"]
    assert view["cleanup"][0]["priority"] == "low"
