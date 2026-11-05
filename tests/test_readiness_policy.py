from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
    ArrayObject,
)

from dayamlchecker.readiness import publication_readiness, REVIEWS

META = "metadata:\n  title: Example\n  short title: Example\n  description: A form\n  authors: [Author]\n  tags: [test]\n  jurisdiction: US-MA\n  can_I_use_this_form: Eligibility\n  before_you_start: Preparation\n"


def package(tmp_path, screens=1, extra=""):
    path = tmp_path / "docassemble/demo/data/questions/main.yml"
    path.parent.mkdir(parents=True)
    source = (
        META
        + "".join(
            f"---\nid: question-{i}\nquestion: Your detail {i}\nfields:\n  - Detail: detail_{i}\n"
            for i in range(screens)
        )
        + extra
    )
    path.write_text(source)
    return path


def check(report, id):
    return next(c for c in report["checks"] if c["id"] == id)


def attest(root):
    report = publication_readiness(root)
    evidence = {"source_sha256": report["source_sha256"]}
    evidence.update(
        {
            key: {
                "passed": True,
                "reviewer": "Author",
                "date": "2026-11-05",
                "evidence": "Static review record",
            }
            for key in REVIEWS
        }
    )
    return publication_readiness(root, evidence=evidence)


def test_short_review_is_warning_and_does_not_prevent_release(tmp_path):
    package(tmp_path)
    report = attest(tmp_path)
    assert report["status"] == "pass"
    review = check(report, "answer_review")
    assert review["status"] == "warning"
    assert review["release_gate"] is False
    assert check(report, "live_testing")["status"] == "not_applicable"
    assert "scenario_testing" not in REVIEWS
    assert "template_review" not in REVIEWS
    assert "accessibility_review" not in REVIEWS


def test_long_review_missing_blocks_but_threshold_is_configurable(tmp_path):
    package(tmp_path, screens=10)
    assert (
        check(publication_readiness(tmp_path), "answer_review")["status"] == "blocked"
    )
    assert (
        check(
            publication_readiness(tmp_path, long_interview_screens=11), "answer_review"
        )["status"]
        == "warning"
    )


def test_review_heading_without_editing_does_not_satisfy_gate(tmp_path):
    package(
        tmp_path,
        screens=10,
        extra="---\nid: review\nquestion: Review your answers\nsubquestion: Your answers are complete.\n",
    )
    assert (
        check(publication_readiness(tmp_path), "answer_review")["status"] == "blocked"
    )


def test_long_review_with_editable_fields_passes_static_gate(tmp_path):
    package(
        tmp_path,
        screens=10,
        extra="---\nid: review\nevent: review_answers\nquestion: Review your answers\nreview:\n  - Edit: detail_0\n    button: Detail\n",
    )
    assert check(publication_readiness(tmp_path), "answer_review")["status"] == "pass"


def test_unresolved_include_does_not_prove_missing_review(tmp_path):
    package(
        tmp_path,
        screens=10,
        extra="---\ninclude:\n  - docassemble.Missing:review.yml\n",
    )
    assert (
        check(publication_readiness(tmp_path), "answer_review")["status"]
        == "needs_review"
    )


def test_missing_prompt_is_question_design_blocker(tmp_path):
    path = package(tmp_path)
    path.write_text(
        path.read_text().replace("question: Your detail 0\n", 'question: ""\n')
    )
    assert (
        check(publication_readiness(tmp_path), "question_design")["status"] == "blocked"
    )


def test_template_labels_and_overflow_are_advisory(tmp_path):
    package(tmp_path)
    path = tmp_path / "docassemble/demo/data/templates/form_draft.pdf"
    path.parent.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    field = DictionaryObject(
        {
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject("Text1"),
            NameObject("/Ff"): NumberObject(4096),
        }
    )
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([writer._add_object(field)])}
    )
    writer.write(path)
    report = attest(tmp_path)
    assert report["status"] == "pass"
    assert check(report, "document_templates")["status"] == "warning"
    assert check(report, "filenames")["status"] == "warning"
    assert not check(report, "document_templates")["release_gate"]


def test_missing_required_local_template_blocks_delivery(tmp_path):
    package(
        tmp_path,
        extra="---\nattachment:\n  name: Form\n  filename: form\n  docx template file: missing.docx\n",
    )
    assert (
        check(publication_readiness(tmp_path), "document_delivery")["status"]
        == "blocked"
    )


def test_style_conventions_are_not_release_blockers(tmp_path):
    path = package(tmp_path)
    path.write_text(path.read_text() + "language: en\n")
    report = attest(tmp_path)
    assert report["status"] == "pass"
    finding = next(
        f for f in report["findings"] if f["message_id"] == "style_remove_language_en"
    )
    assert finding["readiness_severity"] == "warning"
    assert not finding["release_gate"]


def test_supplemental_prompt_without_heading_is_not_automatically_blocked(tmp_path):
    path = package(tmp_path)
    path.write_text(
        path.read_text().replace(
            "question: Your detail 0\n",
            'question: ""\nsubquestion: Tell us about your situation.\n',
        )
    )
    assert check(publication_readiness(tmp_path), "question_design")["status"] == "pass"


def test_bundle_members_are_inspected_without_executing_code(tmp_path):
    package(
        tmp_path,
        extra='---\nobjects:\n  - al_user_bundle: ALDocumentBundle.using(elements=[missing_document], title="Documents")\n',
    )
    delivery = check(publication_readiness(tmp_path), "document_delivery")
    assert delivery["status"] == "warning"
    assert delivery["bundles"][0]["members"] == ["missing_document"]
    assert delivery["notes"][0]["unresolved_members"] == ["missing_document"]
    assert not delivery["release_gate"]


def test_pdf_field_names_need_not_be_interview_variables(tmp_path):
    package(tmp_path)
    path = tmp_path / "docassemble/demo/data/templates/form.pdf"
    path.parent.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    field = DictionaryObject(
        {
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject("applicant_name"),
        }
    )
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([writer._add_object(field)])}
    )
    writer.write(path)
    templates = check(publication_readiness(tmp_path), "document_templates")
    assert not any(
        n["kind"] in {"mapping_unverified", "unreadable_template"}
        for t in templates["templates"]
        for n in t["notes"]
    )


def test_readiness_research_uses_vocabulary_filter(tmp_path, monkeypatch):
    from dayamlchecker import readiness, style
    from dayamlchecker.readiness_research import ResearchOptions

    package(
        tmp_path,
        extra="---\nquestion: Copy the name as it appears on your notice\nfield: name\n",
    )
    calls = []

    def provider(**kwargs):
        import json

        assert kwargs["model"] == "test-terra"
        assert kwargs["user_prompt"].startswith("Triage every vocabulary candidate")
        batch = json.loads(kwargs["user_prompt"].split("\n", 1)[1])
        calls.extend(batch)
        return {
            "decisions": [
                dict(
                    candidate_id=c["candidate_id"],
                    decision="dismiss",
                    confidence="high",
                    reason="Copy the printed text exactly.",
                    evidence=c["text"],
                )
                for c in batch
            ]
        }, None

    monkeypatch.setattr(style, "_call_openai_chat_completion", provider)
    monkeypatch.setattr(
        readiness,
        "research_readiness",
        lambda *a, **k: {
            "status": "pass",
            "execution_status": "complete",
            "model": "test-terra",
            "findings": [],
        },
    )
    report = publication_readiness(
        tmp_path, research=ResearchOptions(model="test-terra", api_key="test")
    )
    assert any(c["term"] == "it appears" for c in calls)
    assert not any(f["code"] == "IS712" for f in report["findings"])


def test_docx_helper_call_is_not_a_missing_answer(tmp_path):
    from tests.test_docx_accessibility import _write_docx, _base_files

    package(tmp_path, extra="---\nobjects:\n  - users: ALPeopleList\n")
    path = tmp_path / "docassemble/demo/data/templates/steps.docx"
    path.parent.mkdir()
    _write_docx(
        path,
        _base_files(
            """<w:document xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Send a copy to {{ showifdef('users[0]') }}.</w:t></w:r></w:p></w:body></w:document>"""
        ),
    )
    templates = check(publication_readiness(tmp_path), "document_templates")
    assert not any(
        n["kind"] in {"mapping_unverified", "unreadable_template"}
        for t in templates["templates"]
        for n in t["notes"]
    )
