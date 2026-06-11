import warnings
from pathlib import Path
from typing import cast

from linkify_it import LinkifyIt  # type: ignore[attr-defined,import-untyped]
from requests import Session

import dayamlchecker.check_questions_urls as check_questions_urls
from dayamlchecker.check_questions_urls import (
    check_urls,
    extract_text_from_docx,
    extract_text_from_pdf,
    extract_urls_from_file,
    parse_url_token,
)


def test_parse_url_token_normalizes_markdown_and_docassemble_artifacts() -> None:
    # Markdown bold
    assert parse_url_token("https://example.com**")[0] == "https://example.com"
    # Docassemble variable prefixes
    assert parse_url_token("https://github.com/$")[0] == "https://github.com/"
    assert parse_url_token("https://github.com/${")[0] == "https://github.com/"
    # Trailing braces
    assert parse_url_token("https://example.com/}")[0] == "https://example.com/"
    # Combined trailing artifacts
    assert parse_url_token("https://example.com/}$")[0] == "https://example.com/"


def test_extract_urls_skips_python_comment_urls(tmp_path: Path) -> None:
    file_path = tmp_path / "suffolklitlab.org.py"
    file_path.write_text(
        "\n".join(
            [
                "# https://commented.suffolklitlab.org/full-line",
                'live = "https://live.suffolklitlab.org/value"',
                "value = 1  # https://commented.suffolklitlab.org/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.suffolklitlab.org/value"]
    assert concatenated == []


def test_extract_urls_skips_yaml_comment_urls(tmp_path: Path) -> None:
    file_path = tmp_path / "suffolklitlab.org.yml"
    file_path.write_text(
        "\n".join(
            [
                "# https://commented.suffolklitlab.org/full-line",
                'live: "https://live.suffolklitlab.org/value"',
                "note: keep # not-a-comment-inside-value",
                "value: yes # https://commented.suffolklitlab.org/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.suffolklitlab.org/value"]
    assert concatenated == []


def test_extract_urls_keeps_urls_in_multiline_double_quoted_yaml_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "suffolklitlab.org.yml"
    file_path.write_text(
        "\n".join(
            [
                'note: "first line',
                "  https://live.suffolklitlab.org/double-quoted",
                '  # still content"',
                "field: value # https://commented.suffolklitlab.org/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.suffolklitlab.org/double-quoted"]
    assert concatenated == []


def test_extract_urls_keeps_urls_in_multiline_single_quoted_yaml_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "suffolklitlab.org.yml"
    file_path.write_text(
        "\n".join(
            [
                "note: 'first line",
                "  https://live.suffolklitlab.org/single-quoted",
                "  it''s still content # not a comment'",
                "field: value # https://commented.suffolklitlab.org/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.suffolklitlab.org/single-quoted"]
    assert concatenated == []


def test_extract_urls_keeps_markdown_heading_urls_in_yaml_block_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "suffolklitlab.org.yml"
    file_path.write_text(
        "\n".join(
            [
                "question: |",
                "  # Heading",
                "  Visit https://live.suffolklitlab.org/question",
                "subquestion: |",
                "  ## Subheading https://live.suffolklitlab.org/subquestion",
                "note: |",
                "  ### Note https://live.suffolklitlab.org/note",
                "field: value # https://commented.suffolklitlab.org/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == [
        "https://live.suffolklitlab.org/question",
        "https://live.suffolklitlab.org/subquestion",
        "https://live.suffolklitlab.org/note",
    ]
    assert concatenated == []


def test_extract_urls_keeps_markdown_heading_urls_in_template_and_attachment_blocks(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "suffolklitlab.org.yml"
    file_path.write_text(
        "\n".join(
            [
                "template: review_email",
                "subject: |",
                "  # Subject https://live.suffolklitlab.org/template-subject",
                "content: |",
                "  ## Content https://live.suffolklitlab.org/template-content",
                "---",
                "attachment:",
                "  name: review_letter",
                "  content: |",
                "    ### Attachment https://live.suffolklitlab.org/attachment-content",
                "  filename: review.pdf",
                "metadata: yes # https://commented.suffolklitlab.org/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == [
        "https://live.suffolklitlab.org/template-subject",
        "https://live.suffolklitlab.org/template-content",
        "https://live.suffolklitlab.org/attachment-content",
    ]
    assert concatenated == []


def test_extract_urls_skips_python_comment_urls_in_code_block_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "suffolklitlab.org.yml"
    file_path.write_text(
        "\n".join(
            [
                "code: |",
                "  # https://commented.suffolklitlab.org/full-line",
                '  live = "https://live.suffolklitlab.org/value"',
                "  value = 1  # https://commented.suffolklitlab.org/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.suffolklitlab.org/value"]
    assert concatenated == []


def test_extract_text_from_pdf_keeps_wrapped_urls_in_raw_text(
    tmp_path: Path, monkeypatch
) -> None:
    file_path = tmp_path / "suffolklitlab.org.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")

    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        def __init__(self, _: Path) -> None:
            self.pages = [
                FakePage(
                    "Visit https://www.courts.michigan.gov/49752a/siteassets/forms/scao-\n"
                    "approved/dhs1201d.pdf for the full form."
                )
            ]

    monkeypatch.setattr(check_questions_urls, "PdfReader", FakeReader)

    assert extract_text_from_pdf(file_path) == (
        "Visit https://www.courts.michigan.gov/49752a/siteassets/forms/scao-\n"
        "approved/dhs1201d.pdf for the full form."
    )


def test_extract_text_from_docx_suppresses_unsupported_none_numbering_warning(
    tmp_path: Path, monkeypatch
) -> None:
    file_path = tmp_path / "template.docx"
    file_path.write_bytes(b"placeholder")

    class FakeResult:
        text = "Visit https://example.com"

    def fake_docx2python(_: Path) -> FakeResult:
        warnings.warn_explicit(
            "none numbering format not implemented, substituting '--'",
            UserWarning,
            filename="bullets_and_numbering.py",
            lineno=291,
            module="docx2python.bullets_and_numbering",
        )
        return FakeResult()

    monkeypatch.setattr(check_questions_urls, "docx2python", fake_docx2python)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert extract_text_from_docx(file_path) == "Visit https://example.com"


def test_extract_text_from_docx_does_not_suppress_other_warnings(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    file_path = tmp_path / "template.docx"
    file_path.write_bytes(b"placeholder")

    def fake_docx2python(_: Path) -> None:
        warnings.warn("unexpected DOCX warning", UserWarning, stacklevel=2)

    monkeypatch.setattr(check_questions_urls, "docx2python", fake_docx2python)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert extract_text_from_docx(file_path) == ""
    assert "unexpected DOCX warning" in capsys.readouterr().err


def test_extract_wrapped_pdf_url_repairs_finds_joined_candidate() -> None:
    repairs = check_questions_urls._extract_wrapped_pdf_url_repairs(
        "Visit https://www.courts.michigan.gov/49752a/siteassets/forms/scao-\n"
        "approved/dhs1201d.pdf for the full form."
    )

    assert repairs == {
        "https://www.courts.michigan.gov/49752a/siteassets/forms/scao-": {
            "https://www.courts.michigan.gov/49752a/siteassets/forms/scao-approved/dhs1201d.pdf"
        }
    }


def test_check_urls_tries_pdf_repair_candidates_after_dead_link() -> None:
    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, **kwargs) -> FakeResponse:
            self.calls.append(url)
            if url.endswith("scao-"):
                return FakeResponse(404)
            if url.endswith("dhs1201d.pdf"):
                return FakeResponse(200)
            raise AssertionError(url)

    session = FakeSession()
    broken, unreachable = check_urls(
        cast(Session, session),
        ["https://www.courts.michigan.gov/49752a/siteassets/forms/scao-"],
        timeout=10,
        repair_candidates={
            "https://www.courts.michigan.gov/49752a/siteassets/forms/scao-": {
                "https://www.courts.michigan.gov/49752a/siteassets/forms/scao-approved/dhs1201d.pdf"
            }
        },
    )

    assert broken == []
    assert unreachable == []
    assert session.calls == [
        "https://www.courts.michigan.gov/49752a/siteassets/forms/scao-",
        "https://www.courts.michigan.gov/49752a/siteassets/forms/scao-approved/dhs1201d.pdf",
    ]
