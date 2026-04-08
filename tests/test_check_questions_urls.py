from pathlib import Path

from linkify_it import LinkifyIt

import dayamlchecker.check_questions_urls as check_questions_urls
from dayamlchecker.check_questions_urls import check_urls, extract_text_from_pdf, extract_urls_from_file


def test_extract_urls_skips_python_comment_urls(tmp_path: Path) -> None:
    file_path = tmp_path / "example.py"
    file_path.write_text(
        "\n".join(
            [
                "# https://commented.example/full-line",
                'live = "https://live.example/value"',
                "value = 1  # https://commented.example/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.example/value"]
    assert concatenated == []


def test_extract_urls_skips_yaml_comment_urls(tmp_path: Path) -> None:
    file_path = tmp_path / "example.yml"
    file_path.write_text(
        "\n".join(
            [
                "# https://commented.example/full-line",
                'live: "https://live.example/value"',
                "note: keep # not-a-comment-inside-value",
                "value: yes # https://commented.example/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.example/value"]
    assert concatenated == []


def test_extract_urls_keeps_markdown_heading_urls_in_yaml_block_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "example.yml"
    file_path.write_text(
        "\n".join(
            [
                "question: |",
                "  # Heading",
                "  Visit https://live.example/question",
                "subquestion: |",
                "  ## Subheading https://live.example/subquestion",
                "note: |",
                "  ### Note https://live.example/note",
                "field: value # https://commented.example/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == [
        "https://live.example/question",
        "https://live.example/subquestion",
        "https://live.example/note",
    ]
    assert concatenated == []


def test_extract_urls_keeps_markdown_heading_urls_in_template_and_attachment_blocks(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "example.yml"
    file_path.write_text(
        "\n".join(
            [
                "template: review_email",
                "subject: |",
                "  # Subject https://live.example/template-subject",
                "content: |",
                "  ## Content https://live.example/template-content",
                "---",
                "attachment:",
                "  name: review_letter",
                "  content: |",
                "    ### Attachment https://live.example/attachment-content",
                "  filename: review.pdf",
                "metadata: yes # https://commented.example/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == [
        "https://live.example/template-subject",
        "https://live.example/template-content",
        "https://live.example/attachment-content",
    ]
    assert concatenated == []


def test_extract_urls_skips_python_comment_urls_in_code_block_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "example.yml"
    file_path.write_text(
        "\n".join(
            [
                "code: |",
                "  # https://commented.example/full-line",
                '  live = "https://live.example/value"',
                "  value = 1  # https://commented.example/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.example/value"]
    assert concatenated == []


def test_extract_text_from_pdf_keeps_wrapped_urls_in_raw_text(
    tmp_path: Path, monkeypatch
) -> None:
    file_path = tmp_path / "example.pdf"
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
        session,
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
