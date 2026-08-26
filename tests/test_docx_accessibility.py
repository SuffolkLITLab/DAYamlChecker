import io
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from dayamlchecker.docx_accessibility import (
    DocxAccessibilityOptions,
    check_docx_accessibility,
)
from dayamlchecker.yaml_structure import main


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


def _accessible_document_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Notice</w:t></w:r></w:p>
    <w:p><w:r><w:t>This document contains enough real text to avoid looking like an image-only scan. It uses meaningful prose and a descriptive link for readers.</w:t></w:r></w:p>
    <w:p><w:hyperlink r:id="rIdLink1"><w:r><w:t>Get filing help</w:t></w:r></w:hyperlink></w:p>
    <w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> HYPERLINK "https://example.com/form" </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>Download the form</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>
    <w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="Logo" descr="Organization logo"/><a:graphic><a:graphicData><pic:pic><pic:nvPicPr><pic:cNvPr id="2" name="logo.png" descr="Organization logo"/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
    <w:tbl>
      <w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Date</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>Ada</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>May 1</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""


def _inaccessible_document_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    <w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="Image 1"/><a:graphic><a:graphicData><pic:pic><pic:nvPicPr><pic:cNvPr id="2" name="image1.png"/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
    <w:p><w:hyperlink r:id="rIdLink1"><w:r><w:t></w:t></w:r></w:hyperlink></w:p>
    <w:p><w:pPr><w:shd w:fill="888888"/></w:pPr><w:r><w:rPr><w:color w:val="777777"/></w:rPr><w:t>Low contrast text</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>Merged</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    <w:p><w:r><w:t>Items marked in red color are required.</w:t></w:r></w:p>
  </w:body>
</w:document>
"""


def test_accessible_docx_has_no_findings():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "accessible.docx"
        _write_docx(path, _base_files(_accessible_document_xml()))

        assert check_docx_accessibility(path) == []


def test_inaccessible_docx_reports_high_confidence_failures_and_warnings():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        files = _base_files(_inaccessible_document_xml(), title="Inaccessible")
        del files["word/styles.xml"]
        _write_docx(path, files)

        findings = check_docx_accessibility(
            path,
            DocxAccessibilityOptions(table_merged_cells_severity="error"),
        )
        by_rule = {finding.rule_id: finding for finding in findings}

        assert by_rule["image-alt-missing"].severity == "error"
        assert by_rule["hyperlink-empty"].severity == "error"
        assert by_rule["contrast-explicit-fail"].severity == "error"
        assert by_rule["table-merged-cells"].severity == "error"
        assert by_rule["document-language-missing"].severity == "error"
        assert by_rule["color-only-risk"].severity == "warning"


def test_unreadable_docx_reports_package_error():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "broken.docx"
        path.write_text("not a zip", encoding="utf-8")

        findings = check_docx_accessibility(path)

        assert len(findings) == 1
        assert findings[0].rule_id == "docx-unreadable"
        assert findings[0].severity == "error"


def test_cli_docx_accessibility_is_optional_and_can_demote_errors():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "inaccessible.docx"
        _write_docx(path, _base_files(_inaccessible_document_xml()))

        disabled_stdout = io.StringIO()
        with redirect_stdout(disabled_stdout):
            disabled_exit = main([str(path)])
        assert disabled_exit == 1
        assert (
            "No YAML files found" in disabled_stdout.getvalue()
            or disabled_stdout.getvalue() == ""
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "--docx-accessibility",
                    "--docx-accessibility-errors-as-warnings",
                    str(path),
                ]
            )

        output = stdout.getvalue().lower()
        assert exit_code == 0
        assert "docx accessibility findings" in output
        assert "[image-alt-missing]" in output
        assert "warnings" in output
