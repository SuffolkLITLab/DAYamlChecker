import io
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from dayamlchecker.docx_accessibility import (
    DocxAccessibilityOptions,
    check_docx_accessibility,
)
from dayamlchecker.messages import Severity
from dayamlchecker.yaml_structure import main

ERROR = Severity.ERROR
WARNING = Severity.WARNING
TIP = Severity.INFO


def _rules(findings) -> dict[str, Severity]:
    """Map rule id (as used in this project's docs) to effective severity."""
    mapped = {}
    for finding in findings:
        rule_id = (
            str(finding.message_id)
            .removeprefix("accessibility_docx_")
            .removesuffix("_warning")
            .replace("_", "-")
        )
        mapped[rule_id] = finding.severity
    return mapped


# Padding long enough that short fixtures are not reported as image-only.
PROSE = (
    "This document contains enough real text to avoid looking like an "
    "image-only scan. It uses meaningful prose so the fixtures below "
    "exercise one rule at a time."
)


def _write_docx(path: Path, files: dict[str, str | bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, content in files.items():
            package.writestr(name, content)


def _base_files(
    document_xml: str, *, title: str = "Accessible Notice"
) -> dict[str, str | bytes]:
    return {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdOffice" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
""",
        "docProps/core.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>{title}</dc:title>
</cp:coreProperties>
""",
        "word/styles.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr><w:lang w:val="en-US"/></w:rPr>
    </w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
    <w:pPr><w:outlineLvl w:val="0"/></w:pPr>
  </w:style>
</w:styles>
""",
        "word/_rels/document.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rIdLink1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/help" TargetMode="External"/>
</Relationships>
""",
        "word/media/image1.png": b"\x89PNG\r\n\x1a\n",
        "word/document.xml": document_xml,
    }


_DOCUMENT_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>%s</w:body>
</w:document>
"""


def _document(body: str) -> str:
    return _DOCUMENT_TEMPLATE % body


def _build(tmp: str, name: str, body: str, **kwargs) -> Path:
    path = Path(tmp) / f"{name}.docx"
    _write_docx(path, _base_files(_document(body), **kwargs))
    return path


def _field_link(target: str, visible: str) -> str:
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText> HYPERLINK "{target}" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"<w:r><w:t>{visible}</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def _accessible_document_xml() -> str:
    return _document(
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Notice</w:t></w:r></w:p>'
        f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>"
        '<w:p><w:hyperlink r:id="rIdLink1"><w:r><w:t>Get filing help</w:t></w:r></w:hyperlink></w:p>'
        "<w:p>"
        + _field_link("https://example.com/form", "Download the form")
        + "</w:p>"
        '<w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="Logo" descr="Organization logo"/>'
        "<a:graphic><a:graphicData><pic:pic><pic:nvPicPr>"
        '<pic:cNvPr id="2" name="logo.png" descr="Organization logo"/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
        "<w:tbl>"
        "<w:tr><w:trPr><w:tblHeader/></w:trPr>"
        "<w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Date</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>Ada</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>May 1</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl>"
    )


def _inaccessible_document_xml() -> str:
    return _document(
        '<w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="Image 1"/>'
        "<a:graphic><a:graphicData><pic:pic><pic:nvPicPr>"
        '<pic:cNvPr id="2" name="image1.png"/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
        '<w:p><w:hyperlink r:id="rIdLink1"><w:r><w:t></w:t></w:r></w:hyperlink></w:p>'
        '<w:p><w:pPr><w:shd w:fill="888888"/></w:pPr>'
        '<w:r><w:rPr><w:color w:val="777777"/></w:rPr><w:t>Low contrast text</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>'
        "<w:p><w:r><w:t>Merged</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "<w:p><w:r><w:t>Items marked in red color are required.</w:t></w:r></w:p>"
    )


# ---------------------------------------------------------------------------
# Baseline behaviour
# ---------------------------------------------------------------------------


def test_accessible_docx_has_no_findings():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "accessible.docx"
        _write_docx(path, _base_files(_accessible_document_xml()))

        assert check_docx_accessibility(path) == []


def test_findings_are_capped_at_warning_by_default():
    """Adopting these checks should annotate a build, not break it."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        files = _base_files(_inaccessible_document_xml(), title="Inaccessible")
        del files["word/styles.xml"]
        _write_docx(path, files)

        findings = check_docx_accessibility(path)

        assert findings, "expected the fixture to produce findings"
        assert not any(finding.severity == ERROR for finding in findings)
        by_rule = _rules(findings)
        assert by_rule["image-alt-missing"] == WARNING
        assert by_rule["hyperlink-empty"] == WARNING
        assert by_rule["contrast-explicit-fail"] == WARNING
        assert by_rule["document-language-missing"] == WARNING


def test_error_severity_is_opt_in():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        files = _base_files(_inaccessible_document_xml(), title="Inaccessible")
        del files["word/styles.xml"]
        _write_docx(path, files)

        findings = check_docx_accessibility(
            path, DocxAccessibilityOptions(max_severity=ERROR)
        )
        by_rule = _rules(findings)

        assert by_rule["image-alt-missing"] == ERROR
        assert by_rule["hyperlink-empty"] == ERROR
        assert by_rule["contrast-explicit-fail"] == ERROR
        assert by_rule["document-language-missing"] == ERROR
        # The ceiling only demotes; it never promotes a rule past its own
        # natural severity, so these stay where they are.
        assert by_rule["table-merged-cells"] == WARNING
        assert by_rule["color-only-risk"] == WARNING


def test_missing_document_title_is_only_a_tip():
    """Nearly every Word file omits it, so it must not drown the real findings."""
    with TemporaryDirectory() as tmp:
        path = _build(tmp, "untitled", f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>")
        files = _base_files(_document(f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>"))
        del files["docProps/core.xml"]
        _write_docx(path, files)

        assert _rules(check_docx_accessibility(path))["document-title-missing"] == TIP


def test_rules_carry_stable_diagnostic_codes():
    """Codes are the handle authors use with --suppress."""
    with TemporaryDirectory() as tmp:
        files = _base_files(_document(f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>"))
        del files["docProps/core.xml"]
        path = Path(tmp) / "untitled.docx"
        _write_docx(path, files)

        findings = check_docx_accessibility(path)
        by_code = {finding.code: finding for finding in findings}

        assert "IA561" in by_code
        assert by_code["IA561"].severity == TIP
        assert by_code["IA561"].finding_class == "accessibility"


def test_unreadable_docx_reports_a_package_finding():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "broken.docx"
        path.write_text("not a zip", encoding="utf-8")

        findings = check_docx_accessibility(path)
        assert len(findings) == 1
        assert _rules(findings) == {"docx-unreadable": WARNING}

        strict = check_docx_accessibility(
            path, DocxAccessibilityOptions(max_severity=ERROR)
        )
        assert strict[0].severity == ERROR


# ---------------------------------------------------------------------------
# Regressions
# ---------------------------------------------------------------------------


def test_outline_level_nine_is_body_text_not_a_heading():
    """w:outlineLvl 0-8 are headings 1-9; 9 explicitly means body text."""
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "outline",
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            "<w:r><w:t>Real heading</w:t></w:r></w:p>"
            '<w:p><w:pPr><w:outlineLvl w:val="9"/></w:pPr>'
            f"<w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        assert "heading-skipped-level" not in _rules(check_docx_accessibility(path))


def test_two_field_hyperlinks_in_one_paragraph_stay_separate():
    """Each field's visible text is its own, not the whole paragraph's."""
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "two_links",
            "<w:p>"
            + _field_link("https://example.com/a", "form A")
            + "<w:r><w:t> and </w:t></w:r>"
            + _field_link("https://example.com/b", "form B")
            + "</w:p>"
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        assert "link-ambiguous" not in _rules(check_docx_accessibility(path))


def test_ambiguous_field_link_inside_a_sentence_is_caught():
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "click_here",
            "<w:p><w:r><w:t>For details about fees, please </w:t></w:r>"
            + _field_link("https://example.com/a", "click here")
            + "<w:r><w:t> before you go to the courthouse.</w:t></w:r></w:p>"
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        assert _rules(check_docx_accessibility(path))["link-ambiguous"] == WARNING


def test_contrast_is_checked_inside_hyperlink_runs():
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "link_contrast",
            '<w:p><w:pPr><w:shd w:fill="888888"/></w:pPr>'
            '<w:hyperlink r:id="rIdLink1">'
            '<w:r><w:rPr><w:color w:val="777777"/></w:rPr>'
            "<w:t>Low contrast link text</w:t></w:r></w:hyperlink></w:p>"
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        assert (
            _rules(check_docx_accessibility(path))["contrast-explicit-fail"] == WARNING
        )


def test_bold_toggled_off_uses_the_small_text_contrast_threshold():
    """<w:b w:val="0"/> is bold OFF, so 14pt text is not "large text"."""
    body = (
        '<w:p><w:pPr><w:shd w:fill="FFFFFF"/></w:pPr>'
        '<w:r><w:rPr>%s<w:sz w:val="28"/><w:color w:val="949494"/></w:rPr>'
        "<w:t>Grey text at fourteen points</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>"
    )
    with TemporaryDirectory() as tmp:
        # 3.03:1 clears the 3.0 large-text bar but fails the 4.5 body-text bar.
        off = _build(tmp, "bold_off", body % '<w:b w:val="0"/>')
        assert "contrast-explicit-fail" in _rules(check_docx_accessibility(off))

        on = _build(tmp, "bold_on", body % "<w:b/>")
        assert "contrast-explicit-fail" not in _rules(check_docx_accessibility(on))


def test_nested_table_cells_are_not_blamed_on_the_outer_table():
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "nested",
            "<w:tbl>"
            "<w:tr><w:trPr><w:tblHeader/></w:trPr>"
            "<w:tc><w:p><w:r><w:t>H1</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>H2</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:tbl>"
            "<w:tr><w:tc><w:p><w:r><w:t>inner a</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>inner b</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:p><w:r><w:t>inner c</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>inner d</w:t></w:r></w:p></w:tc></w:tr>"
            "</w:tbl></w:tc>"
            "<w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        assert "table-merged-cells" not in _rules(check_docx_accessibility(path))


def test_vml_image_alt_text_is_recognized():
    with TemporaryDirectory() as tmp:
        with_alt = _build(
            tmp,
            "vml_alt",
            '<w:p><w:r><w:pict><v:shape id="s1" alt="Seal of the court">'
            '<v:imagedata r:id="rIdImage1"/></v:shape></w:pict></w:r></w:p>'
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )
        assert "image-alt-missing" not in _rules(check_docx_accessibility(with_alt))

        without_alt = _build(
            tmp,
            "vml_no_alt",
            '<w:p><w:r><w:pict><v:shape id="s1">'
            '<v:imagedata r:id="rIdImage1"/></v:shape></w:pict></w:r></w:p>'
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )
        assert "image-alt-missing" in _rules(check_docx_accessibility(without_alt))


def test_short_documents_are_not_faulted_for_having_no_headings():
    """A one-page court form legitimately has no heading styles."""
    with TemporaryDirectory() as tmp:
        short = _build(tmp, "short", f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>")
        assert "heading-none" not in _rules(check_docx_accessibility(short))

        long_body = "".join(
            f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>" for _ in range(12)
        )
        long = _build(tmp, "long", long_body)
        assert "heading-none" in _rules(check_docx_accessibility(long))


def test_findings_name_nearby_text_so_they_can_be_located():
    """A DOCX has no line numbers, so messages must say where to look."""
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "locatable",
            "<w:tbl>"
            "<w:tr><w:tc><w:p><w:r><w:t>Household income</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>Amount</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:p><w:r><w:t>Wages</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>100</w:t></w:r></w:p></w:tc></w:tr>"
            "</w:tbl>"
            f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        messages = {f.code: f.message for f in check_docx_accessibility(path)}

        assert 'table begins "Household income"' in messages["WA552"]


def test_empty_paragraph_findings_quote_the_text_beside_them():
    body = (
        "<w:p><w:r><w:t>Signature of Petitioner</w:t></w:r></w:p>"
        + "<w:p/>" * 6
        + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>"
    )
    with TemporaryDirectory() as tmp:
        path = _build(tmp, "spacing", body)

        messages = {f.code: f.message for f in check_docx_accessibility(path)}

        assert "6 empty paragraphs" in messages["IA565"]
        assert "longest run being 6" in messages["IA565"]
        assert 'near "Signature of Petitioner"' in messages["IA565"]


def test_images_are_located_by_the_text_around_them():
    image = (
        '<w:r><w:drawing><wp:inline><wp:docPr id="1" name="Image 1"/>'
        "<a:graphic><a:graphicData><pic:pic><pic:nvPicPr>"
        '<pic:cNvPr id="2" name="image1.png"/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
    )
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "images",
            "<w:p><w:r><w:t>Step 3: mail the form</w:t></w:r></w:p>"
            f"<w:p>{image}</w:p>"
            f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        alt_missing = [f for f in check_docx_accessibility(path) if f.code == "WA541"]

        assert len(alt_missing) == 1
        assert 'near "Step 3: mail the form"' in alt_missing[0].message


def test_two_problem_tables_are_reported_separately():
    """Without locating context these would collapse into one finding."""

    def table(first_cell: str) -> str:
        return (
            "<w:tbl>"
            f"<w:tr><w:tc><w:p><w:r><w:t>{first_cell}</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>b</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:p><w:r><w:t>c</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>d</w:t></w:r></w:p></w:tc></w:tr>"
            "</w:tbl>"
        )

    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "two_tables",
            table("Income")
            + table("Expenses")
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        no_header = [f for f in check_docx_accessibility(path) if f.code == "WA552"]

        assert len(no_header) == 2
        assert {'table begins "Income"' in f.message for f in no_header} == {
            True,
            False,
        }


def test_context_is_omitted_when_there_is_no_nearby_text():
    """The suffix must vanish rather than render an empty quote."""
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "bare",
            "<w:tbl>"
            "<w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc></w:tr>"
            "<w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc></w:tr>"
            "</w:tbl>"
            f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        for finding in check_docx_accessibility(path):
            assert '""' not in finding.message
            assert "(near )" not in finding.message


def test_long_nearby_text_is_truncated_to_one_line():
    sentence = "The petitioner must file this motion with the clerk of the court "
    with TemporaryDirectory() as tmp:
        path = _build(
            tmp,
            "long_context",
            f"<w:p><w:r><w:t>{sentence * 4}</w:t></w:r></w:p>"
            + "<w:p/>" * 6
            + f"<w:p><w:r><w:t>{PROSE}</w:t></w:r></w:p>",
        )

        message = next(
            f.message for f in check_docx_accessibility(path) if f.code == "IA565"
        )
        excerpt = message.split('near "')[1].rstrip('")')

        assert len(excerpt) <= 81, excerpt
        assert excerpt.endswith("\u2026")
        assert excerpt.startswith("The petitioner must file")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_cli(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(argv)
    return exit_code, stdout.getvalue()


def test_cli_checks_docx_by_default_without_failing():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        _write_docx(path, _base_files(_inaccessible_document_xml()))

        exit_code, output = _run_cli(["--no-url-check", str(path)])

        assert exit_code == 0, "warning-level findings must not fail the build"
        assert "0 errors" in output
        assert "WA541" in output, "image-alt-missing, demoted to a warning"


def test_cli_can_skip_docx_checks():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        _write_docx(path, _base_files(_inaccessible_document_xml()))

        exit_code, _ = _run_cli(
            ["--no-docx-accessibility", "--no-url-check", str(path)]
        )

        assert exit_code == 1, "nothing left to check"


def test_cli_error_severity_fails_the_command():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        _write_docx(path, _base_files(_inaccessible_document_xml()))

        exit_code, output = _run_cli(
            ["--docx-accessibility-severity", "error", "--no-url-check", str(path)]
        )

        assert exit_code == 1
        assert "EA541" in output


def test_cli_suppress_silences_a_rule_by_code():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        _write_docx(path, _base_files(_inaccessible_document_xml()))

        _, output = _run_cli(["--suppress", "WA541", "--no-url-check", str(path)])

        assert "WA541" not in output


def test_cli_github_format_annotates_the_document():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        _write_docx(path, _base_files(_inaccessible_document_xml()))

        exit_code, output = _run_cli(
            ["--format", "github", "--no-url-check", str(path)]
        )

        assert exit_code == 0
        assert f"::warning file={path},title=WA541::" in output
        assert "::error" not in output
        # Annotations are consumed by the runner; the log needs a summary.
        assert "Found " in output and "0 errors" not in output


def test_cli_github_format_errors_when_opted_in():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        _write_docx(path, _base_files(_inaccessible_document_xml()))

        exit_code, output = _run_cli(
            [
                "--format",
                "github",
                "--docx-accessibility-severity",
                "error",
                "--no-url-check",
                str(path),
            ]
        )

        assert exit_code == 1
        assert f"::error file={path},title=EA541::" in output
