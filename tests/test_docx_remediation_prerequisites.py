"""Checker behavior required by consumers that store files under opaque names."""

import pytest
from test_docx_accessibility import _base_files, _document, _write_docx
from dayamlchecker.docx_accessibility import (
    check_docx_accessibility,
    DocxAccessibilityOptions,
)
from dayamlchecker.messages import Severity

OPTIONS = DocxAccessibilityOptions(max_severity=Severity.ERROR)


def check(tmp_path, files, **kwargs):
    path = tmp_path / "uuid.docx"
    _write_docx(path, files)
    return check_docx_accessibility(path, OPTIONS, **kwargs)


def test_malformed_required_and_optional_xml(tmp_path):
    for part in ["word/document.xml", "word/header1.xml"]:
        files = _base_files(_document("<w:p><w:r><w:t>Body text</w:t></w:r></w:p>"))
        files[part] = "<broken"
        findings = check(tmp_path, files)
        assert any(f.code == "EA540" and f.context["part"] == part for f in findings)


def test_unused_style_does_not_establish_effective_language(tmp_path):
    files = _base_files(_document("<w:p><w:r><w:t>Body text</w:t></w:r></w:p>"))
    files["word/styles.xml"] = (
        """<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:styleId="Unused"><w:rPr><w:lang w:val="en-US"/></w:rPr></w:style></w:styles>"""
    )
    assert any(f.code == "EA545" for f in check(tmp_path, files))
    files["word/document.xml"] = _document(
        '<w:p><w:pPr><w:pStyle w:val="Unused"/></w:pPr><w:r><w:t>Body text</w:t></w:r></w:p>'
    )
    assert not any(f.code == "EA545" for f in check(tmp_path, files))


@pytest.mark.parametrize(
    "value,missing",
    [
        ("0", True),
        ("false", True),
        ("off", True),
        ("1", False),
        ("true", False),
        ("on", False),
        ("", False),
    ],
)
def test_header_toggle_and_duplicate_table_targets(tmp_path, value, missing):
    marker = f'<w:tblHeader w:val="{value}"/>' if value else "<w:tblHeader/>"
    table = f"<w:tbl><w:tr><w:trPr>{marker}</w:trPr><w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>County</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>Ada</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Suffolk</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    findings = check(tmp_path, _base_files(_document(table + table)))
    headers = [f for f in findings if f.code == "WA552"]
    assert len(headers) == (2 if missing else 0)
    if missing:
        assert headers[0].context["element_path"] != headers[1].context["element_path"]


def test_logical_filename_and_invalid_severity(tmp_path):
    files = _base_files(_document("<w:p><w:r><w:t>Body text</w:t></w:r></w:p>"))
    assert any(
        f.code == "IA562"
        for f in check(tmp_path, files, logical_filename="document.docx")
    )
    assert not any(
        f.code == "IA562"
        for f in check(tmp_path, files, logical_filename="Housing application.docx")
    )
    with pytest.raises(ValueError):
        DocxAccessibilityOptions(max_severity=Severity.INFO)
