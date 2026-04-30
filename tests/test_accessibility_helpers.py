from pathlib import Path
from unittest.mock import patch

import pytest

import dayamlchecker.accessibility as accessibility


def test_find_accessibility_findings_deduplicates_identical_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finding = accessibility.AccessibilityFinding(
        rule_id="duplicate-rule",
        message="Accessibility: duplicate",
        line_number=3,
    )
    monkeypatch.setattr(
        accessibility,
        "_check_multifield_no_label_usage",
        lambda doc, document_start_line: [finding, finding],
    )
    monkeypatch.setattr(
        accessibility, "_check_combobox_usage", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(accessibility, "_check_tagged_pdf_for_docx", lambda *args: [])
    monkeypatch.setattr(
        accessibility, "_check_theme_css_contrast", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(accessibility, "_iter_text_sections", lambda *args: [])

    assert accessibility.find_accessibility_findings(
        doc={}, source_code="", document_start_line=1
    ) == [finding]


def test_combobox_check_skips_non_combobox_fields_when_enabled() -> None:
    findings = accessibility._check_combobox_usage(
        {"fields": [{"Name": "user_name", "datatype": "text"}]},
        "question: Hi\nfields:\n  - Name: user_name\n",
        1,
        options=accessibility.AccessibilityLintOptions(
            error_on_widgets=frozenset({"combobox"})
        ),
    )

    assert findings == []


def test_tagged_pdf_attachment_edge_cases() -> None:
    dict_attachment = accessibility._check_tagged_pdf_for_docx(
        {"attachments": {"template file": "letter.docx"}},
        "attachments:\n  template file: letter.docx\n",
        1,
    )
    skipped_attachments = accessibility._check_tagged_pdf_for_docx(
        {
            "attachments": [
                "not a dict",
                {"name": "No template"},
                {"docx template file": "letter.docx", "tagged pdf": "yes"},
            ]
        },
        "attachments: []\n",
        1,
    )

    assert len(dict_attachment) == 1
    assert skipped_attachments == []


def test_text_sections_and_accessible_media_are_skipped() -> None:
    source = """question: |
  ![Logo](logo.png)
  [FILE logo.png, 100px, Logo]
  <img src="logo.png" alt="Logo">
under:
  content: <a href="/go" aria-label="Continue"></a>
help:
  label: Help text
"""
    sections = accessibility._iter_text_sections(
        {
            "question": '![Logo](logo.png)\n[FILE logo.png, 100px, Logo]\n<img src="logo.png" alt="Logo">',
            "under": {"content": '<a href="/go" aria-label="Continue"></a>'},
            "help": {"label": "Help text"},
        },
        source,
    )

    assert [section.location for section in sections] == [
        "question",
        "under.content",
        "help.label",
    ]
    assert accessibility._check_missing_alt_text(sections[0], source, 1) == []
    assert accessibility._check_empty_link_text(sections[1], source, 1) == []


def test_line_field_truthy_and_attachment_helpers() -> None:
    assert accessibility._find_top_level_key_line("question: Hi\n", "missing") is None
    assert accessibility._absolute_line_number("question: Hi\n", 10, 1, "absent") == 10
    assert accessibility._find_snippet_line("question: Hi\n", "") is None
    assert accessibility._find_snippet_line("question: Hi\n", "absent") is None
    assert accessibility._iter_fields({"fields": {"Name": "user_name"}}) == [
        {"Name": "user_name"}
    ]
    assert accessibility._extract_field_variable({"Name": "user_name"}) == "user_name"
    assert (
        accessibility._extract_field_variable({"Age": 42, "Name": "user_name"})
        == "user_name"
    )
    assert accessibility._extract_field_label({"label": "Explicit"}) == "Explicit"
    assert accessibility._is_truthy(1)
    assert not accessibility._is_truthy(0)
    assert accessibility._is_truthy("yes")
    assert not accessibility._is_truthy("no")
    assert accessibility._attachment_uses_docx({"template": "letter.docx"})
    assert accessibility._attachment_uses_docx({"filename": "letter.docx"})
    assert not accessibility._attachment_uses_docx({"filename": "letter.pdf"})


def test_bootstrap_theme_css_loader_paths_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    theme = tmp_path / "theme.css"
    theme.write_text("body { color: #000; background: #fff; }", encoding="utf-8")
    interview = tmp_path / "questions" / "interview.yml"
    interview.parent.mkdir()
    relative_theme = interview.parent / "relative.css"
    relative_theme.write_text(
        "body { color: #111; background: #fff; }", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert accessibility._load_bootstrap_theme_css("", input_file=None) is None
    assert (
        accessibility._load_bootstrap_theme_css(
            "https://example.com/theme.css", input_file=None
        )
        is None
    )
    assert accessibility._load_bootstrap_theme_css(
        str(theme), input_file=None
    ) == theme.read_text(encoding="utf-8")
    assert accessibility._load_bootstrap_theme_css(
        "relative.css", input_file=str(interview)
    ) == relative_theme.read_text(encoding="utf-8")
    assert (
        accessibility._load_bootstrap_theme_css(
            "missing.css", input_file=str(interview)
        )
        is None
    )

    with patch.object(accessibility.Path, "exists", side_effect=OSError):
        assert (
            accessibility._load_bootstrap_theme_css(str(theme), input_file=None) is None
        )


def test_theme_contrast_skips_missing_css_and_unmatched_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_css = accessibility._check_theme_css_contrast(
        {"features": {"bootstrap theme": "missing.css"}},
        "features:\n  bootstrap theme: missing.css\n",
        1,
    )
    assert missing_css == []

    monkeypatch.setattr(
        accessibility,
        "_load_bootstrap_theme_css",
        lambda *args, **kwargs: ".unrelated { color: #777; background: #777; }",
    )
    unmatched = accessibility._check_theme_css_contrast(
        {"features": {"bootstrap theme": "theme.css"}},
        "features:\n  bootstrap theme: theme.css\n",
        1,
    )
    assert unmatched == []


def test_css_parsing_and_color_helpers() -> None:
    selector_props, variables = accessibility._parse_css_rules(
        ".empty { } :root { --fg: #abc; } .body { color: var(--fg); }"
    )
    assert variables == {"--fg": "#abc"}
    assert selector_props
    assert accessibility._best_component_color_pair(
        [
            (["body"], {"color": "#000"}),
            (["body"], {"background-color": "#fff"}),
        ],
        {},
        ["body"],
    ) == ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    assert (
        accessibility._best_component_color_pair(
            [([".other"], {"color": "#000"})], {}, ["body"]
        )
        is None
    )
    assert accessibility._parse_css_declarations(
        "color: #000; background: #fff; ignored"
    ) == {
        "color": "#000",
        "background": "#fff",
    }
    assert accessibility._parse_css_declarations(": missing; color: #000") == {
        "color": "#000"
    }

    assert accessibility._resolve_css_color(None, {}) is None
    assert accessibility._resolve_css_color("var(--missing, #fff)", {}) == (
        1.0,
        1.0,
        1.0,
    )
    assert accessibility._resolve_css_color("var(--missing)", {}) is None
    assert accessibility._resolve_css_color("not-a-color", {}) is None
    assert accessibility._resolve_css_color("#abc", {}) == pytest.approx(
        (170 / 255, 187 / 255, 204 / 255)
    )
    assert accessibility._resolve_css_color("rgb(10, 20, 30)", {}) == pytest.approx(
        (10 / 255, 20 / 255, 30 / 255)
    )
    assert accessibility._resolve_css_color("rgb(10, 20)", {}) is None
    assert accessibility._resolve_css_color("rgb(nope, 20, 30)", {}) is None
    assert accessibility._resolve_css_color("black", {}) == (0.0, 0.0, 0.0)
    assert accessibility._resolve_css_color("white", {}) == (1.0, 1.0, 1.0)
    assert accessibility._resolve_css_color("rebeccapurple", {}) is None

    assert accessibility._extract_color_token("#abc") == "#abc"
    assert accessibility._extract_color_token("rgb(1, 2, 3)") == "rgb(1, 2, 3)"
    assert accessibility._extract_color_token("var(--fg)") == "var(--fg)"
    assert accessibility._extract_color_token("border: #abcdef,") == "#abcdef"
    assert accessibility._extract_color_token("color rgb(4,5,6)") == "rgb(4,5,6)"
    assert accessibility._extract_color_token("color black") == "black"
    assert accessibility._extract_color_token("none") is None

    assert accessibility._parse_rgb_channel("50%") == 0.5
    assert accessibility._parse_rgb_channel("300") == 1.0
    assert accessibility._parse_rgb_channel("-5") == 0.0
    assert accessibility._relative_luminance((0.0, 0.0, 0.0)) == 0.0


def test_extract_color_token_loop_rgb_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    real_rgb_re = accessibility._RGB_COLOR_RE

    class DelayedRgbRegex:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, value: str):
            self.calls += 1
            if self.calls == 1:
                return None
            return real_rgb_re.search(value)

    monkeypatch.setattr(accessibility, "_RGB_COLOR_RE", DelayedRgbRegex())

    assert accessibility._extract_color_token("color rgb(4,5,6)") == "rgb(4,5,6)"


def test_extract_links_from_text_includes_html_attributes() -> None:
    links = accessibility._extract_links_from_text(
        '[Label](https://example.com) <a href="/next" title="Next title">Next</a>'
    )

    assert links == [
        {
            "kind": "markdown",
            "text": "Label",
            "target": "https://example.com",
            "aria_label": "",
            "title": "",
            "snippet": "[Label](https://example.com)",
        },
        {
            "kind": "html",
            "text": "Next",
            "target": "/next",
            "aria_label": "",
            "title": "Next title",
            "snippet": '<a href="/next" title="Next title">Next</a>',
        },
    ]
