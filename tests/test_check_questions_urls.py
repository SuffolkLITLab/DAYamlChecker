from pathlib import Path

from linkify_it import LinkifyIt

from dayamlchecker.check_questions_urls import extract_urls_from_file


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
