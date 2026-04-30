import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import requests
from linkify_it import LinkifyIt  # type: ignore[attr-defined,import-untyped]
from requests import Session

import dayamlchecker.check_questions_urls as check_questions_urls
from dayamlchecker.check_questions_urls import (
    URLCheckResult,
    URLIssue,
    URLSourceCollection,
    build_session,
    check_urls,
    collect_urls,
    collect_urls_from_files,
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_urls_from_file,
    infer_root,
    iter_document_files,
    iter_question_files,
    parse_args,
    parse_ignore_urls,
    parse_url_token,
    print_url_check_report,
    run_url_check,
)


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


def test_extract_urls_keeps_urls_in_multiline_double_quoted_yaml_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "example.yml"
    file_path.write_text(
        "\n".join(
            [
                'note: "first line',
                "  https://live.example/double-quoted",
                '  # still content"',
                "field: value # https://commented.example/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.example/double-quoted"]
    assert concatenated == []


def test_extract_urls_keeps_urls_in_multiline_single_quoted_yaml_scalar(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "example.yml"
    file_path.write_text(
        "\n".join(
            [
                "note: 'first line",
                "  https://live.example/single-quoted",
                "  it''s still content # not a comment'",
                "field: value # https://commented.example/trailing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    urls, concatenated = extract_urls_from_file(
        file_path, LinkifyIt(options={"fuzzy_link": False})
    )

    assert urls == ["https://live.example/single-quoted"]
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


def test_extract_text_from_pdf_skips_empty_page_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
            self.pages = [FakePage(""), FakePage("Kept text")]

    monkeypatch.setattr(check_questions_urls, "PdfReader", FakeReader)

    assert extract_text_from_pdf(file_path) == "Kept text"


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


def test_extract_wrapped_pdf_url_repairs_skips_non_repair_lines() -> None:
    assert (
        check_questions_urls._extract_wrapped_pdf_url_repairs(
            "Visit https://example.org/complete\nnext line"
        )
        == {}
    )
    assert (
        check_questions_urls._extract_wrapped_pdf_url_repairs(
            "Visit https://example.org/path-\nhttps://example.org/other"
        )
        == {}
    )


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


def test_url_result_helpers_report_warnings_and_unique_urls() -> None:
    result = URLCheckResult(
        checked_url_count=1,
        ignored_url_count=0,
        issues=(
            URLIssue(
                severity="warning",
                category="unreachable",
                source_kind="yaml",
                url="https://down.example",
                sources=("question.yml",),
            ),
        ),
    )
    collection = URLSourceCollection(
        yaml_urls={"https://a.example": {"question.yml"}},
        document_urls={
            "https://a.example": {"template.docx"},
            "https://b.example": {"template.docx"},
        },
        yaml_concatenated={},
        document_concatenated={},
        yaml_repairs={},
        document_repairs={},
    )

    assert result.has_warnings()
    assert collection.unique_url_count == 2


def test_parse_args_reads_all_url_checker_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_questions_urls",
            "--root",
            "project",
            "--timeout",
            "3",
            "--skip-templates",
            "--ignore-urls",
            "https://ignore.example",
            "--question-url-severity",
            "warning",
            "--template-url-severity",
            "error",
            "--document-url-severity",
            "ignore",
            "--unreachable-url-severity",
            "error",
        ],
    )

    args = parse_args()

    assert args.root == "project"
    assert args.timeout == 3
    assert args.skip_templates is True
    assert args.ignore_urls == "https://ignore.example"
    assert args.yaml_url_severity == "warning"
    assert args.document_url_severity == "ignore"
    assert args.unreachable_url_severity == "error"


def test_package_dir_iterators_handle_supplied_and_discovered_dirs(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing-root"
    assert list(check_questions_urls._iter_package_dirs(missing_root)) == []

    package_dir = tmp_path / "docassemble" / "Demo"
    package_dir.mkdir(parents=True)
    (tmp_path / "docassemble" / "not-a-package.txt").write_text("x", encoding="utf-8")
    assert list(check_questions_urls._iter_package_dirs(tmp_path)) == [package_dir]

    supplied_missing = tmp_path / "missing"
    assert list(
        check_questions_urls._iter_package_dirs(
            tmp_path, package_dirs=[package_dir, package_dir, supplied_missing]
        )
    ) == [package_dir.resolve()]


def test_question_and_document_file_iterators_filter_suffixes(tmp_path: Path) -> None:
    package_dir = tmp_path / "docassemble" / "Demo"
    questions = package_dir / "data" / "questions"
    templates = package_dir / "data" / "templates"
    questions.mkdir(parents=True)
    templates.mkdir(parents=True)
    question_file = questions / "interview.yml"
    ignored_question = questions / "image.png"
    template_pdf = templates / "letter.pdf"
    template_text = templates / "letter.md"
    ignored_template = templates / "archive.zip"
    for file_path in [
        question_file,
        ignored_question,
        template_pdf,
        template_text,
        ignored_template,
    ]:
        file_path.write_text("x", encoding="utf-8")

    assert list(iter_question_files(tmp_path)) == [question_file]
    assert set(iter_document_files(tmp_path)) == {template_pdf, template_text}

    empty_package = tmp_path / "docassemble" / "Empty"
    empty_package.mkdir()
    assert list(iter_question_files(tmp_path, package_dirs=[empty_package])) == []
    assert list(iter_document_files(tmp_path, package_dirs=[empty_package])) == []


def test_infer_root_uses_docassemble_parent_common_parent_fallback_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_file = tmp_path / "docassemble" / "Demo" / "data" / "questions" / "a.yml"
    package_file.parent.mkdir(parents=True)
    package_file.write_text("question: Hi", encoding="utf-8")
    outside_root = tmp_path.parent / f"{tmp_path.name}-outside-root"
    outside_one = outside_root / "outside" / "one.yml"
    outside_two = outside_root / "outside" / "nested" / "two.yml"
    outside_one.parent.mkdir(parents=True)
    outside_two.parent.mkdir()
    outside_one.write_text("x", encoding="utf-8")
    outside_two.write_text("x", encoding="utf-8")

    assert infer_root([package_file]) == tmp_path
    assert infer_root([outside_one, outside_two]) == outside_one.parent
    assert infer_root([], fallback=outside_one) == outside_one.resolve()
    monkeypatch.chdir(tmp_path)
    assert infer_root([]) == tmp_path


def test_build_session_sets_retrying_user_agent() -> None:
    session = build_session()

    assert "ALActions-da_build-url-checker" in session.headers["User-Agent"]
    assert "https://" in session.adapters


def test_extract_text_from_pdf_and_docx_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf_path = tmp_path / "bad.pdf"
    docx_path = tmp_path / "bad.docx"
    pdf_path.write_bytes(b"not really a pdf")
    docx_path.write_bytes(b"not really a docx")

    class BrokenReader:
        def __init__(self, _: Path) -> None:
            raise RuntimeError("pdf exploded")

    def broken_docx(_: Path) -> object:
        raise RuntimeError("docx exploded")

    monkeypatch.setattr(check_questions_urls, "PdfReader", BrokenReader)
    monkeypatch.setattr(check_questions_urls, "docx2python", broken_docx)

    assert extract_text_from_pdf(pdf_path) == ""
    assert extract_text_from_docx(docx_path) == ""
    err = capsys.readouterr().err
    assert "could not extract text from PDF" in err
    assert "could not extract text from DOCX" in err


def test_extract_text_from_docx_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docx_path = tmp_path / "ok.docx"
    docx_path.write_bytes(b"docx")

    monkeypatch.setattr(
        check_questions_urls,
        "docx2python",
        lambda _: SimpleNamespace(text="Text from document"),
    )

    assert extract_text_from_docx(docx_path) == "Text from document"


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        ("", (None, False)),
        ("www.example.com", (None, False)),
        ("https://a.example/pathhttps://b.example", (None, True)),
        ('https://a.example/"quoted"', (None, False)),
        ("https:///missing-host", (None, False)),
        (
            "https://a.example/form?next=https://nested.example/path#frag",
            ("https://a.example/form", False),
        ),
        ("https://a.example/path).", ("https://a.example/path", False)),
    ],
)
def test_parse_url_token_edge_cases(
    raw_url: str, expected: tuple[str | None, bool]
) -> None:
    assert parse_url_token(raw_url) == expected


def test_parse_ignore_urls_skips_empty_and_malformed_values() -> None:
    assert parse_ignore_urls("") == set()
    assert parse_ignore_urls(
        "\nhttps://keep.example, https://bad.examplehttps://other.example, not-a-url"
    ) == {"https://keep.example"}


def test_comment_strippers_handle_token_errors_and_empty_blocks() -> None:
    incomplete_python = "value = '''unterminated"

    assert (
        check_questions_urls._strip_python_comments(incomplete_python)
        == incomplete_python
    )
    assert check_questions_urls._extract_wrapped_pdf_url_repairs("one line only") == {}
    assert (
        check_questions_urls._strip_python_comments_from_indented_block(["\n", "   \n"])
        == "\n   \n"
    )


def test_yaml_comment_stripping_handles_escaped_quotes_and_block_boundaries() -> None:
    text = "\n".join(
        [
            'title: "He said \\"# not a comment\\"" # comment',
            "code: |",
            "  # python comment",
            "  live = 'https://live.example'",
            "next: value # trailing",
            "",
        ]
    )

    stripped = check_questions_urls._strip_yaml_comments(text)

    assert "# python comment" not in stripped
    assert "https://live.example" in stripped
    assert "# trailing" not in stripped
    assert check_questions_urls._is_unescaped_double_quote('x = "quoted"', 4)
    assert not check_questions_urls._is_unescaped_double_quote('x = \\"escaped"', 5)


def test_prepare_and_extract_urls_from_non_text_document_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linkify = LinkifyIt(options={"fuzzy_link": False})
    binary_path = tmp_path / "binary.yml"
    binary_path.write_bytes(b"\xff\xfe")
    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.write_bytes(b"pdf")
    docx_path = tmp_path / "links.docx"
    docx_path.write_bytes(b"docx")
    text_path = tmp_path / "links.txt"
    text_path.write_text(
        "https://example.com/reserved https://ok.test/path https://bad.test/ahttps://bad.test/b",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_questions_urls, "extract_text_from_pdf", lambda _: "")
    monkeypatch.setattr(
        check_questions_urls, "extract_text_from_docx", lambda _: "https://doc.test"
    )

    assert (
        check_questions_urls._prepare_text_for_url_extraction(text_path, "a # b")
        == "a # b"
    )
    assert check_questions_urls._extract_urls_from_file_detailed(
        binary_path, linkify
    ) == ([], [], {})
    assert check_questions_urls._extract_urls_from_file_detailed(
        empty_pdf, linkify
    ) == ([], [], {})
    assert check_questions_urls._extract_urls_from_file_detailed(
        docx_path, linkify
    ) == (
        ["https://doc.test"],
        [],
        {},
    )
    urls, concatenated, repairs = check_questions_urls._extract_urls_from_file_detailed(
        text_path, linkify
    )
    assert urls == ["https://ok.test/path"]
    assert concatenated == ["https://bad.test/ahttps://bad.test/b"]
    assert repairs == {}


def test_extract_urls_from_file_detailed_skips_matches_without_valid_urls(
    tmp_path: Path,
) -> None:
    text_path = tmp_path / "links.txt"
    text_path.write_text("placeholder", encoding="utf-8")

    class FakeLinkify:
        def match(self, text: str):
            return [SimpleNamespace(url="mailto:help@example.org")]

    assert check_questions_urls._extract_urls_from_file_detailed(
        text_path, cast(LinkifyIt, FakeLinkify())
    ) == ([], [], {})


def test_collect_urls_from_files_tracks_sources_concatenated_and_repairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.yml"
    second = tmp_path / "second.yml"
    first.write_text("x", encoding="utf-8")
    second.write_text("x", encoding="utf-8")

    def fake_extract(
        file_path: Path, linkify: LinkifyIt
    ) -> tuple[list[str], list[str], dict[str, set[str]]]:
        if file_path == first:
            return (
                ["https://one.test"],
                ["https://bad.testhttps://other.test"],
                {"https://one.test": {"https://fixed.test"}},
            )
        return ["https://one.test", "https://two.test"], [], {}

    monkeypatch.setattr(
        check_questions_urls, "_extract_urls_from_file_detailed", fake_extract
    )

    urls, concatenated, repairs = collect_urls_from_files([first, second], tmp_path)

    assert urls == {
        "https://one.test": {"first.yml", "second.yml"},
        "https://two.test": {"second.yml"},
    }
    assert concatenated == {"https://bad.testhttps://other.test": {"first.yml"}}
    assert repairs == {"https://one.test": {"https://fixed.test"}}


def test_collect_urls_defaults_question_files_and_can_skip_documents(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "docassemble" / "Demo"
    questions = package_dir / "data" / "questions"
    templates = package_dir / "data" / "templates"
    questions.mkdir(parents=True)
    templates.mkdir(parents=True)
    (questions / "interview.yml").write_text(
        "question: https://question.test", encoding="utf-8"
    )
    (templates / "letter.md").write_text("https://template.test", encoding="utf-8")

    with_documents = collect_urls(tmp_path)
    without_documents = collect_urls(tmp_path, check_documents=False)

    assert with_documents.yaml_urls == {
        "https://question.test": {"docassemble/Demo/data/questions/interview.yml"}
    }
    assert with_documents.document_urls == {
        "https://template.test": {"docassemble/Demo/data/templates/letter.md"}
    }
    assert without_documents.document_urls == {}


def test_check_single_url_reports_or_suppresses_unreachable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingSession:
        def get(self, url: str, **kwargs) -> object:
            raise requests.Timeout("too slow")

    status, unreachable = check_questions_urls._check_single_url(
        cast(Session, FailingSession()), "https://slow.test", 1
    )
    assert (status, unreachable) == (None, True)
    assert "could not check https://slow.test" in capsys.readouterr().err

    status, unreachable = check_questions_urls._check_single_url(
        cast(Session, FailingSession()),
        "https://slow.test",
        1,
        report_unreachable=False,
    )
    assert (status, unreachable) == (None, True)
    assert capsys.readouterr().err == ""


def test_check_urls_covers_skip_unreachable_broken_and_repair_paths() -> None:
    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeSession:
        def get(self, url: str, **kwargs) -> FakeResponse:
            if url == "https://unreachable.test":
                raise requests.ConnectionError("offline")
            if url == "https://ok.test":
                return FakeResponse(200)
            if url in {
                "https://broken.test",
                "https://repair-whitelisted.test",
                "https://repair-bad.test",
                "https://repair-unreachable.test",
                "https://still-bad.test",
            }:
                return FakeResponse(404)
            if url == "https://repair-candidate-unreachable.test":
                raise requests.Timeout("offline")
            raise AssertionError(url)

    broken, unreachable = check_urls(
        cast(Session, FakeSession()),
        [
            "https://api.openai.com/v1/chat/completions",
            "https://broken.test",
            "https://ok.test",
            "https://repair-bad.test",
            "https://repair-unreachable.test",
            "https://repair-whitelisted.test",
            "https://unreachable.test",
        ],
        timeout=1,
        repair_candidates={
            "https://repair-whitelisted.test": {"https://api.openai.com/v1/models"},
            "https://repair-bad.test": {"https://still-bad.test"},
            "https://repair-unreachable.test": {
                "https://repair-candidate-unreachable.test"
            },
        },
    )

    assert broken == [
        ("https://broken.test", 404),
        ("https://repair-bad.test", 404),
        ("https://repair-unreachable.test", 404),
    ]
    assert unreachable == ["https://unreachable.test"]


def test_append_issue_respects_ignore_and_document_severity() -> None:
    issues: list[URLIssue] = []

    check_questions_urls._append_issue(
        issues,
        category="broken",
        source_kind="yaml",
        url="https://ignored.test",
        sources={"question.yml"},
        yaml_severity="ignore",
        document_severity="warning",
        unreachable_severity="warning",
    )
    check_questions_urls._append_issue(
        issues,
        category="broken",
        source_kind="template",
        url="https://template.test",
        sources={"template.docx"},
        yaml_severity="error",
        document_severity="warning",
        unreachable_severity="error",
        status_code=410,
    )

    assert issues == [
        URLIssue(
            severity="warning",
            category="broken",
            source_kind="template",
            url="https://template.test",
            sources=("template.docx",),
            status_code=410,
        )
    ]


def test_run_url_check_builds_sorted_issues_for_all_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collected = URLSourceCollection(
        yaml_urls={
            "https://ignored.test": {"question.yml"},
            "https://broken-yaml.test": {"question.yml"},
            "https://unreachable-yaml.test": {"question.yml"},
            "https://shared-broken.test": {"question.yml"},
        },
        document_urls={
            "https://ignored.test": {"template.docx"},
            "https://broken-template.test": {"template.docx"},
            "https://unreachable-template.test": {"template.docx"},
            "https://shared-broken.test": {"template.docx"},
        },
        yaml_concatenated={"https://bad-yaml.testhttps://other.test": {"question.yml"}},
        document_concatenated={
            "https://bad-template.testhttps://other.test": {"template.docx"}
        },
        yaml_repairs={"https://broken-yaml.test": {"https://fixed-yaml.test"}},
        document_repairs={
            "https://broken-template.test": {"https://fixed-template.test"}
        },
    )
    captured_repairs: dict[str, set[str]] = {}

    monkeypatch.setattr(
        check_questions_urls, "collect_urls", lambda **kwargs: collected
    )
    monkeypatch.setattr(check_questions_urls, "build_session", lambda: object())

    def fake_check_urls(
        session: object,
        urls: set[str],
        timeout: int,
        repair_candidates: dict[str, set[str]],
    ):
        captured_repairs.update(repair_candidates)
        return (
            [
                ("https://broken-yaml.test", 404),
                ("https://broken-template.test", 410),
                ("https://shared-broken.test", 404),
            ],
            ["https://unreachable-yaml.test", "https://unreachable-template.test"],
        )

    monkeypatch.setattr(check_questions_urls, "check_urls", fake_check_urls)

    result = run_url_check(root=tmp_path, ignore_urls=["https://ignored.test"])

    assert result.checked_url_count == 5
    assert result.ignored_url_count == 1
    assert captured_repairs["https://broken-yaml.test"] == {"https://fixed-yaml.test"}
    assert [
        (issue.category, issue.source_kind, issue.url) for issue in result.issues
    ] == [
        ("concatenated", "yaml", "https://bad-yaml.testhttps://other.test"),
        ("broken", "yaml", "https://broken-yaml.test"),
        ("broken", "yaml", "https://shared-broken.test"),
        ("concatenated", "template", "https://bad-template.testhttps://other.test"),
        ("broken", "template", "https://broken-template.test"),
        ("broken", "template", "https://shared-broken.test"),
        ("unreachable", "yaml", "https://unreachable-yaml.test"),
        ("unreachable", "template", "https://unreachable-template.test"),
    ]


def test_run_url_check_skips_network_when_no_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        check_questions_urls,
        "collect_urls",
        lambda **kwargs: URLSourceCollection({}, {}, {}, {}, {}, {}),
    )
    monkeypatch.setattr(
        check_questions_urls,
        "build_session",
        lambda: pytest.fail("session should not be built without URLs"),
    )

    assert run_url_check(root=tmp_path).checked_url_count == 0


def test_print_url_check_report_covers_empty_success_and_issue_buckets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_url_check_report(
        URLCheckResult(checked_url_count=0, ignored_url_count=1, issues=())
    )
    output = capsys.readouterr().out
    assert "Ignoring 1 URL" in output
    assert "No absolute URLs found" in output

    print_url_check_report(
        URLCheckResult(checked_url_count=2, ignored_url_count=0, issues=())
    )
    assert "Checked 2 URLs" in capsys.readouterr().out

    print_url_check_report(
        URLCheckResult(
            checked_url_count=3,
            ignored_url_count=0,
            issues=(
                URLIssue(
                    "error",
                    "broken",
                    "yaml",
                    "https://broken.test",
                    ("question.yml",),
                    404,
                ),
                URLIssue(
                    "warning",
                    "unreachable",
                    "template",
                    "https://slow.test",
                    ("template.docx",),
                ),
            ),
        )
    )
    output = capsys.readouterr().out
    assert "URL checker errors" in output
    assert "[404] https://broken.test" in output
    assert "URL checker warnings" in output
    assert "https://slow.test (found in: template.docx)" in output


def test_main_wires_args_and_returns_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    args = SimpleNamespace(
        root=str(tmp_path),
        timeout=7,
        skip_templates=True,
        ignore_urls="https://ignore.test",
        yaml_url_severity="warning",
        document_url_severity="ignore",
        unreachable_url_severity="error",
    )
    captured: dict[str, object] = {}
    result = URLCheckResult(
        checked_url_count=1,
        ignored_url_count=0,
        issues=(
            URLIssue("error", "broken", "yaml", "https://bad.test", ("q.yml",), 404),
        ),
    )

    def fake_run_url_check(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr(check_questions_urls, "parse_args", lambda: args)
    monkeypatch.setattr(check_questions_urls, "run_url_check", fake_run_url_check)
    monkeypatch.setattr(check_questions_urls, "print_url_check_report", lambda _: None)

    assert check_questions_urls.main() == 1
    assert captured == {
        "root": tmp_path.resolve(),
        "timeout": 7,
        "check_documents": False,
        "ignore_urls": {"https://ignore.test"},
        "yaml_severity": "warning",
        "document_severity": "ignore",
        "unreachable_severity": "error",
    }

    monkeypatch.setattr(
        check_questions_urls,
        "run_url_check",
        lambda **kwargs: URLCheckResult(0, 0, ()),
    )
    assert check_questions_urls.main() == 0


def test_module_main_guard_exits_with_main_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_questions_urls.py",
            "--root",
            str(tmp_path),
            "--skip-templates",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path(check_questions_urls.__file__)), run_name="__main__")

    assert exc_info.value.code == 0
    assert "No absolute URLs found" in capsys.readouterr().out
