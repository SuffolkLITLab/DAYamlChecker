from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import zipfile
from typing import Optional
import xml.etree.ElementTree as ET

from dayamlchecker.messages import Finding, MessageId, Severity

_WORD_PART_RE = re.compile(
    r"^word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$"
)
_RAW_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_MANUAL_NUMBERING_RE = re.compile(r"^\s*(?:\d+|[a-zA-Z])[\.\)]\s+\S+")
_COLOR_ONLY_RE = re.compile(
    r"\b(?:red|green|blue|yellow|orange|purple|gray|grey)\b", re.IGNORECASE
)
_PLACEHOLDER_ALT = {
    "",
    "image",
    "picture",
    "photo",
    "graphic",
    "screenshot",
    "todo",
    "tbd",
    "alt text",
}
_GENERIC_TITLES = {"document", "report", "untitled"}
_AMBIGUOUS_LINK_TEXT = {"click here", "here", "read more", "more", "link"}
_GENERIC_FILENAMES = {"document", "doc", "file", "untitled", "template", "draft"}
_IMAGE_EXTENSIONS = {
    ".bmp",
    ".dib",
    ".emf",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".wmf",
}
_HIGHLIGHT_COLORS = {
    "black": "000000",
    "blue": "0000FF",
    "cyan": "00FFFF",
    "green": "008000",
    "magenta": "FF00FF",
    "red": "FF0000",
    "yellow": "FFFF00",
    "white": "FFFFFF",
    "darkBlue": "000080",
    "darkCyan": "008080",
    "darkGreen": "006400",
    "darkMagenta": "800080",
    "darkRed": "800000",
    "darkYellow": "808000",
    "darkGray": "808080",
    "lightGray": "C0C0C0",
}
_WCAG_SRGB_LINEAR_THRESHOLD = 0.04045
_WCAG_SRGB_DIVISOR = 12.92
_WCAG_SRGB_OFFSET = 0.055
_WCAG_SRGB_SCALE = 1.055
_WCAG_SRGB_EXPONENT = 2.4
_WCAG_CONTRAST_OFFSET = 0.05
# Below this much body text a document is short enough (a one-page court form,
# a caption fragment) that having no heading styles is not a real finding.
_HEADING_REQUIRED_TEXT_LENGTH = 1500

_SEVERITY_RANK = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2}


def _message_id(rule_id: str, severity: Severity) -> str:
    """Look up the MessageId registered for a rule at a given severity.

    Rules whose natural severity is ERROR also register a WARNING variant so
    the severity ceiling can demote them without inventing a message.
    """
    name = "ACCESSIBILITY_DOCX_" + rule_id.replace("-", "_").upper()
    if severity == Severity.WARNING and hasattr(MessageId, f"{name}_WARNING"):
        name = f"{name}_WARNING"
    return getattr(MessageId, name)


@dataclass(frozen=True)
class DocxAccessibilityOptions:
    """Severity policy for the DOCX checks.

    `max_severity` is a ceiling every finding is clamped to. It defaults to
    WARNING so a repo turning these checks on gets annotations rather than a
    red build; raise it to ERROR to opt into failing on inaccessible output.
    Individual rules are silenced with the CLI's `--suppress`, which works by
    diagnostic code across every checker.
    """

    max_severity: Severity = Severity.WARNING

    def message_id(self, rule_id: str, natural: Severity) -> str:
        severity = natural
        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[self.max_severity]:
            severity = self.max_severity
        return _message_id(rule_id, severity)


@dataclass(frozen=True)
class _Relationship:
    target: str
    target_mode: str
    rel_type: str


@dataclass(frozen=True)
class _StyleInfo:
    style_id: str
    name: str = ""
    based_on: str = ""
    outline_level: Optional[int] = None
    is_default_run: bool = False
    color: Optional[str] = None
    size_half_points: Optional[int] = None
    bold: bool = False


def check_docx_accessibility(
    path: str | Path, options: Optional[DocxAccessibilityOptions] = None
) -> list[Finding]:
    options = options or DocxAccessibilityOptions()
    path = Path(path)
    document = str(path)

    try:
        with zipfile.ZipFile(path) as package:
            names = set(package.namelist())
            if "word/document.xml" not in names:
                return [
                    _finding(
                        options,
                        document,
                        "docx-unreadable",
                        Severity.ERROR,
                        "package",
                        detail="the package is missing word/document.xml",
                    )
                ]
            return _DocxContext(package, names, path).check(options)
    except (OSError, zipfile.BadZipFile):
        return [
            _finding(
                options,
                document,
                "docx-unreadable",
                Severity.ERROR,
                "package",
                detail="the file is not a valid DOCX ZIP package",
            )
        ]


def collect_docx_files(
    paths: list[Path], include_default_ignores: bool = True
) -> list[Path]:
    ignored = {".hg", ".mypy_cache", ".pytest_cache", "__pycache__", ".venv", "venv"}
    if include_default_ignores:
        ignored.update({"build", "dist", "node_modules", "sources"})
    found: set[Path] = set()
    for path in paths:
        path = path.resolve()
        if path.is_file() and path.suffix.lower() == ".docx":
            found.add(path)
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*.docx"):
            if include_default_ignores and _has_ignored_path_part(candidate, ignored):
                continue
            found.add(candidate.resolve())
    return sorted(found)


class _DocxContext:
    def __init__(self, package: zipfile.ZipFile, names: set[str], path: Path) -> None:
        self.package = package
        self.names = names
        self.path = path
        self.document = str(path)
        self.relationships: dict[str, dict[str, _Relationship]] = {}
        self.styles: dict[str, _StyleInfo] = {}
        self.default_run_style = _StyleInfo(style_id="", is_default_run=True)

    def check(self, options: DocxAccessibilityOptions) -> list[Finding]:
        findings: list[Finding] = []
        self.relationships = {
            part_name: self._load_relationships(part_name)
            for part_name in self.names
            if part_name.endswith(".xml")
        }
        self._load_styles()

        content_parts = [
            name for name in sorted(self.names) if _WORD_PART_RE.match(name)
        ]
        roots: dict[str, ET.Element] = {}
        for part_name in content_parts:
            root = self._xml_root(part_name)
            if root is not None:
                roots[part_name] = root

        findings.extend(self._check_package_metadata(options))
        findings.extend(self._check_document_language(options))
        all_text = []
        heading_levels: list[tuple[int, str]] = []
        alt_texts: list[str] = []
        empty_paragraphs = 0
        manual_numbering_count = 0

        for part_name, root in roots.items():
            findings.extend(
                self._check_drawings_and_objects(part_name, root, options, alt_texts)
            )
            findings.extend(self._check_hyperlinks(part_name, root, options))
            table_findings = self._check_tables(part_name, root, options)
            findings.extend(table_findings)
            findings.extend(self._check_reading_order_risks(part_name, root, options))
            contrast_findings = self._check_contrast(part_name, root, options)
            findings.extend(contrast_findings)

            for paragraph in _descendants(root, "p"):
                paragraph_text = _element_text(paragraph)
                if paragraph_text.strip():
                    all_text.append(paragraph_text.strip())
                    if _MANUAL_NUMBERING_RE.match(paragraph_text):
                        manual_numbering_count += 1
                else:
                    empty_paragraphs += 1
                heading = self._paragraph_heading_level(paragraph)
                if heading is None:
                    continue
                heading_levels.append((heading, paragraph_text))
                if not paragraph_text.strip():
                    findings.append(
                        _finding(
                            options,
                            self.document,
                            "heading-empty",
                            Severity.WARNING,
                            part_name,
                        )
                    )
                if (
                    paragraph_text.strip().isupper()
                    and len(paragraph_text.strip()) >= 8
                ):
                    findings.append(
                        _finding(
                            options,
                            self.document,
                            "all-caps-heading",
                            Severity.INFO,
                            part_name,
                        )
                    )

        document_text = " ".join(all_text)
        findings.extend(
            self._check_headings(heading_levels, len(document_text), options)
        )
        findings.extend(self._check_document_text_risks(document_text, options))
        findings.extend(
            self._check_tips(
                alt_texts, empty_paragraphs, manual_numbering_count, options
            )
        )
        return _unique_findings(findings)

    def _xml_root(self, name: str) -> Optional[ET.Element]:
        try:
            return ET.fromstring(self.package.read(name))
        except (ET.ParseError, KeyError):
            return None

    def _load_relationships(self, part_name: str) -> dict[str, _Relationship]:
        rels_name = _rels_name_for_part(part_name)
        if rels_name not in self.names:
            return {}
        root = self._xml_root(rels_name)
        if root is None:
            return {}
        rels: dict[str, _Relationship] = {}
        for rel in list(root):
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            if not rel_id:
                continue
            rels[rel_id] = _Relationship(
                target=target,
                target_mode=rel.attrib.get("TargetMode", ""),
                rel_type=rel.attrib.get("Type", ""),
            )
        return rels

    def _load_styles(self) -> None:
        root = self._xml_root("word/styles.xml")
        if root is None:
            return
        doc_defaults = _first_descendant(root, "docDefaults")
        if doc_defaults is not None:
            run_props = _first_descendant(doc_defaults, "rPr")
            self.default_run_style = _run_style_info(run_props, "")
        for style in _descendants(root, "style"):
            style_id = _attr(style, "styleId")
            if not style_id:
                continue
            name_el = _first_child(style, "name")
            based_on_el = _first_child(style, "basedOn")
            outline_el = _first_descendant(style, "outlineLvl")
            run_props = _first_child(style, "rPr")
            run_info = _run_style_info(run_props, style_id)
            self.styles[style_id] = _StyleInfo(
                style_id=style_id,
                name=_attr(name_el, "val") if name_el is not None else "",
                based_on=_attr(based_on_el, "val") if based_on_el is not None else "",
                outline_level=(
                    _parse_int(_attr(outline_el, "val"))
                    if outline_el is not None
                    else None
                ),
                color=run_info.color,
                size_half_points=run_info.size_half_points,
                bold=run_info.bold,
            )

    def _check_package_metadata(
        self, options: DocxAccessibilityOptions
    ) -> list[Finding]:
        findings: list[Finding] = []
        title = ""
        root = self._xml_root("docProps/core.xml")
        if root is not None:
            for element in root.iter():
                if _local_name(element.tag) == "title":
                    title = _element_text(element).strip()
                    break
        filename_stem = self.path.stem.strip().lower()
        if not title:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "document-title-missing",
                    Severity.INFO,
                    "docProps/core.xml",
                    detail="Document title metadata is missing",
                )
            )
        elif (
            title.strip().lower() == filename_stem
            or title.strip().lower() in _GENERIC_TITLES
        ):
            findings.append(
                _finding(
                    options,
                    self.document,
                    "document-title-missing",
                    Severity.INFO,
                    "docProps/core.xml",
                    detail="Document title metadata is generic or repeats the filename",
                )
            )
        if filename_stem in _GENERIC_FILENAMES:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "filename-not-descriptive",
                    Severity.INFO,
                    "package",
                )
            )
        return findings

    def _check_document_language(
        self, options: DocxAccessibilityOptions
    ) -> list[Finding]:
        if _has_language_in_style_defaults(self.package, self.names):
            return []
        settings = self._xml_root("word/settings.xml")
        if (
            settings is not None
            and _first_descendant(settings, "themeFontLang") is not None
        ):
            return []
        return [
            _finding(
                options,
                self.document,
                "document-language-missing",
                Severity.ERROR,
                "word/styles.xml",
            )
        ]

    def _check_drawings_and_objects(
        self,
        part_name: str,
        root: ET.Element,
        options: DocxAccessibilityOptions,
        alt_texts: list[str],
    ) -> list[Finding]:
        findings: list[Finding] = []
        candidates = (
            list(_descendants(root, "drawing"))
            + list(_descendants(root, "pict"))
            + list(_descendants(root, "object"))
        )
        rels = self.relationships.get(part_name, {})
        for element in candidates:
            alt_values = _accessible_names(element)
            alt_texts.extend(alt_values)
            decorative = _is_decorative(element)
            is_image = _element_has_image_reference(element, rels)
            has_accessible_name = any(value.strip() for value in alt_values)

            if decorative and has_accessible_name:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "decorative-image-has-alt",
                        Severity.WARNING,
                        part_name,
                    )
                )

            if is_image:
                if not has_accessible_name and not decorative:
                    findings.append(
                        _finding(
                            options,
                            self.document,
                            "image-alt-missing",
                            Severity.ERROR,
                            part_name,
                        )
                    )
                for alt in alt_values:
                    if _is_placeholder_alt(alt, rels):
                        findings.append(
                            _finding(
                                options,
                                self.document,
                                "image-alt-placeholder",
                                Severity.WARNING,
                                part_name,
                                alt=alt,
                            )
                        )
                continue

            if _element_has_non_image_object(element) and not has_accessible_name:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "object-alt-missing",
                        Severity.ERROR,
                        part_name,
                    )
                )
        return findings

    def _check_hyperlinks(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[Finding]:
        findings: list[Finding] = []
        rels = self.relationships.get(part_name, {})
        text_to_targets: dict[str, set[str]] = {}
        target_to_texts: dict[str, set[str]] = {}
        links: list[tuple[str, str]] = []

        for link in _descendants(root, "hyperlink"):
            target = ""
            rel_id = _attr(link, "id")
            if rel_id and rel_id in rels:
                target = rels[rel_id].target
            elif _attr(link, "anchor"):
                target = "#" + _attr(link, "anchor")
            visible = _element_text(link).strip()
            if not target:
                continue
            links.append((visible, target))

        for simple in _descendants(root, "fldSimple"):
            instr = _attr(simple, "instr") or ""
            target = _hyperlink_target_from_instruction(instr)
            if target:
                links.append((_element_text(simple).strip(), target))

        for paragraph in _descendants(root, "p"):
            links.extend(_field_hyperlinks(paragraph))

        for visible, target in links:
            normalized = _normalize_text(visible)
            if not normalized:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "hyperlink-empty",
                        Severity.ERROR,
                        part_name,
                        target=target,
                    )
                )
                continue
            text_to_targets.setdefault(normalized, set()).add(target)
            target_to_texts.setdefault(target, set()).add(normalized)
            if _RAW_URL_RE.match(visible.strip()):
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "link-raw-url",
                        Severity.WARNING,
                        part_name,
                        link_text=visible.strip(),
                    )
                )
            if normalized in _AMBIGUOUS_LINK_TEXT:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "link-ambiguous",
                        Severity.WARNING,
                        part_name,
                        detail=f'Link text is ambiguous: "{visible.strip()}"',
                    )
                )

        for text, link_targets in text_to_targets.items():
            if len(link_targets) > 1:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "link-ambiguous",
                        Severity.WARNING,
                        part_name,
                        detail=f'Link text "{text}" points to multiple URLs',
                    )
                )
        for target, texts in target_to_texts.items():
            if len(texts) > 1:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "link-same-url-different-text",
                        Severity.INFO,
                        part_name,
                        target=target,
                    )
                )
        return findings

    def _check_tables(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[Finding]:
        findings: list[Finding] = []
        for table in _descendants(root, "tbl"):
            rows = list(_children(table, "tr"))
            # Only this table's own cells; a nested table's cells belong to it,
            # not to the parent, for merge and empty-cell ratio purposes.
            cells = [cell for row in rows for cell in _children(row, "tc")]
            has_nested_table = any(
                _first_descendant(cell, "tbl") is not None for cell in cells
            )
            has_header = any(
                _first_descendant(row, "tblHeader") is not None for row in rows[:1]
            )
            has_merged = any(_is_merged_cell(cell) for cell in cells)
            if has_merged:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "table-merged-cells",
                        Severity.WARNING,
                        part_name,
                    )
                )
            if has_nested_table:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "table-layout-suspected",
                        Severity.WARNING,
                        part_name,
                        detail="Nested table found; verify it is not being used for layout",
                    )
                )
            if len(rows) >= 2 and len(cells) >= 4 and not has_header:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "table-no-header-row",
                        Severity.WARNING,
                        part_name,
                    )
                )
            empty_cells = [cell for cell in cells if not _element_text(cell).strip()]
            if len(cells) >= 4 and len(empty_cells) / max(len(cells), 1) >= 0.5:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "table-layout-suspected",
                        Severity.WARNING,
                        part_name,
                        detail="Table has many empty cells and may be used for layout",
                    )
                )
        return findings

    def _check_reading_order_risks(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[Finding]:
        findings: list[Finding] = []
        if _first_descendant(root, "anchor") is not None:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "floating-object-detected",
                    Severity.WARNING,
                    part_name,
                )
            )
        risky_names = {
            "txbxContent": "text-box-detected",
            "textbox": "text-box-detected",
            "chart": "floating-object-detected",
            # SmartArt surfaces as dgm:relIds/dgm:dataModel, not "smartArt".
            "relIds": "floating-object-detected",
            "dataModel": "floating-object-detected",
        }
        seen_rules = set()
        for element in root.iter():
            rule_id = risky_names.get(_local_name(element.tag))
            if not rule_id or rule_id in seen_rules:
                continue
            seen_rules.add(rule_id)
            message = (
                "Text box found; reading order may be problematic"
                if rule_id == "text-box-detected"
                else "Floating object detected; verify reading order in Word"
            )
            findings.append(
                _finding(
                    options,
                    self.document,
                    rule_id,
                    Severity.WARNING,
                    part_name,
                )
            )
        return findings

    def _check_contrast(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[Finding]:
        findings: list[Finding] = []
        seen_paragraphs: set[int] = set()
        for cell in _descendants(root, "tc"):
            cell_bg = _shading_fill(_first_child(cell, "tcPr"))
            for paragraph in _descendants(cell, "p"):
                seen_paragraphs.add(id(paragraph))
                findings.extend(
                    self._check_paragraph_contrast(
                        part_name, paragraph, options, cell_bg
                    )
                )
        for paragraph in _descendants(root, "p"):
            if id(paragraph) in seen_paragraphs:
                continue
            findings.extend(
                self._check_paragraph_contrast(part_name, paragraph, options, None)
            )
        return findings

    def _check_paragraph_contrast(
        self,
        part_name: str,
        paragraph: ET.Element,
        options: DocxAccessibilityOptions,
        inherited_bg: Optional[str],
    ) -> list[Finding]:
        paragraph_bg = _shading_fill(_first_child(paragraph, "pPr")) or inherited_bg
        findings: list[Finding] = []
        # Descendants, not children: runs are commonly wrapped in w:hyperlink,
        # w:ins, or w:smartTag, and link text is a frequent contrast failure.
        for run in _descendants(paragraph, "r"):
            text = _element_text(run).strip()
            if not text:
                continue
            run_props = _first_child(run, "rPr")
            fg = _run_color(run_props)
            bg = _highlight_fill(run_props) or _shading_fill(run_props) or paragraph_bg
            if fg is None:
                style_info = self._style_for_run(run_props)
                fg = style_info.color
            if not fg or not bg:
                continue
            fg_rgb = _rgb_from_hex(fg)
            bg_rgb = _rgb_from_hex(bg)
            if fg_rgb is None or bg_rgb is None:
                continue
            ratio = _contrast_ratio(fg_rgb, bg_rgb)
            run_info = _run_style_info(run_props, "")
            style_info = self._style_for_run(run_props)
            size = (
                run_info.size_half_points
                or style_info.size_half_points
                or self.default_run_style.size_half_points
            )
            bold = run_info.bold or style_info.bold
            threshold = 3.0 if _is_large_text(size, bold) else 4.5
            if ratio < threshold:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "contrast-explicit-fail",
                        Severity.ERROR,
                        part_name,
                        ratio=f"{ratio:.2f}",
                        threshold=f"{threshold:.1f}",
                    )
                )
        return findings

    def _style_for_run(self, run_props: Optional[ET.Element]) -> _StyleInfo:
        if run_props is None:
            return self.default_run_style
        style_el = _first_child(run_props, "rStyle")
        style_id = _attr(style_el, "val") if style_el is not None else ""
        return self._resolve_style(style_id) if style_id else self.default_run_style

    def _resolve_style(
        self, style_id: str, seen: Optional[set[str]] = None
    ) -> _StyleInfo:
        seen = seen or set()
        style = self.styles.get(style_id)
        if style is None or style_id in seen:
            return self.default_run_style
        seen.add(style_id)
        parent = (
            self._resolve_style(style.based_on, seen)
            if style.based_on
            else self.default_run_style
        )
        return _StyleInfo(
            style_id=style.style_id,
            name=style.name or parent.name,
            based_on=style.based_on,
            outline_level=(
                style.outline_level
                if style.outline_level is not None
                else parent.outline_level
            ),
            color=style.color or parent.color,
            size_half_points=style.size_half_points or parent.size_half_points,
            bold=style.bold or parent.bold,
        )

    def _paragraph_heading_level(self, paragraph: ET.Element) -> Optional[int]:
        p_props = _first_child(paragraph, "pPr")
        if p_props is None:
            return None
        outline = _first_child(p_props, "outlineLvl")
        if outline is not None:
            return _heading_level_from_outline(_attr(outline, "val"))
        style_el = _first_child(p_props, "pStyle")
        style_id = _attr(style_el, "val") if style_el is not None else ""
        if not style_id:
            return None
        style = self._resolve_style(style_id)
        if style.outline_level is not None:
            level = _heading_level_from_outline(str(style.outline_level))
            if level is not None:
                return level
        if style_id.lower().startswith("heading"):
            return _trailing_int(style_id)
        if style.name.lower().startswith("heading"):
            return _trailing_int(style.name)
        return None

    def _check_headings(
        self,
        heading_levels: list[tuple[int, str]],
        text_length: int,
        options: DocxAccessibilityOptions,
    ) -> list[Finding]:
        findings: list[Finding] = []
        if not heading_levels and text_length >= _HEADING_REQUIRED_TEXT_LENGTH:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "heading-none",
                    Severity.WARNING,
                    "word/document.xml",
                )
            )
            return findings
        if heading_levels and heading_levels[0][0] > 1:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "heading-order-starts-too-low",
                    Severity.WARNING,
                    "word/document.xml",
                    level=heading_levels[0][0],
                )
            )
        for (previous_level, _), (current_level, text) in zip(
            heading_levels, heading_levels[1:]
        ):
            if current_level <= previous_level + 1:
                continue
            findings.append(
                _finding(
                    options,
                    self.document,
                    "heading-skipped-level",
                    Severity.WARNING,
                    "word/document.xml",
                    previous_level=previous_level,
                    level=current_level,
                    heading_text=text.strip(),
                )
            )
            break
        return findings

    def _check_document_text_risks(
        self, document_text: str, options: DocxAccessibilityOptions
    ) -> list[Finding]:
        findings: list[Finding] = []
        word_count = len(document_text.split())
        image_refs = 0
        for part_name in self.names:
            if part_name.startswith("word/media/"):
                image_refs += 1
        if image_refs > 0 and word_count < 20:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "image-only-document",
                    Severity.WARNING,
                    "word/document.xml",
                )
            )
        lowered = document_text.lower()
        if "color" in lowered and _COLOR_ONLY_RE.search(lowered):
            findings.append(
                _finding(
                    options,
                    self.document,
                    "color-only-risk",
                    Severity.WARNING,
                    "word/document.xml",
                )
            )
        return findings

    def _check_tips(
        self,
        alt_texts: list[str],
        empty_paragraphs: int,
        manual_numbering_count: int,
        options: DocxAccessibilityOptions,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for alt in alt_texts:
            if len(alt.split()) >= 30 or len(alt) >= 180:
                findings.append(
                    _finding(
                        options,
                        self.document,
                        "long-alt-text",
                        Severity.INFO,
                        "word/document.xml",
                    )
                )
        if empty_paragraphs >= 5:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "many-empty-paragraphs",
                    Severity.INFO,
                    "word/document.xml",
                )
            )
        if manual_numbering_count >= 3:
            findings.append(
                _finding(
                    options,
                    self.document,
                    "manual-numbering-detected",
                    Severity.INFO,
                    "word/document.xml",
                )
            )
        return findings


def _finding(
    options: DocxAccessibilityOptions,
    document: str,
    rule_id: str,
    natural_severity: Severity,
    part: str,
    **context: object,
) -> Finding:
    return Finding(
        message_id=options.message_id(rule_id, natural_severity),
        file_name=document,
        context={"document": document, "part": part, **context},
    )


def _unique_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse findings that would render identically.

    A rule that fires on every table in a document should be reported once,
    not once per table -- there is no line number to tell them apart.
    """
    unique: list[Finding] = []
    seen: set[tuple[str, str | None, str]] = set()
    for finding in findings:
        key = (finding.message_id, finding.file_name, finding.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _rels_name_for_part(part_name: str) -> str:
    path = Path(part_name)
    parent = str(path.parent)
    return f"{parent}/_rels/{path.name}.rels"


def _has_ignored_path_part(path: Path, ignored: set[str]) -> bool:
    for part in path.parts:
        if part in ignored or part.startswith(".git") or part.startswith(".github"):
            return True
    return False


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _attr(element: Optional[ET.Element], local_name: str) -> str:
    if element is None:
        return ""
    for key, value in element.attrib.items():
        if _local_name(key) == local_name:
            return value
    return ""


def _children(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == local_name]


def _descendants(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in element.iter() if _local_name(child.tag) == local_name]


def _first_child(
    element: Optional[ET.Element], local_name: str
) -> Optional[ET.Element]:
    if element is None:
        return None
    for child in list(element):
        if _local_name(child.tag) == local_name:
            return child
    return None


def _first_descendant(
    element: Optional[ET.Element], local_name: str
) -> Optional[ET.Element]:
    if element is None:
        return None
    for child in element.iter():
        if _local_name(child.tag) == local_name:
            return child
    return None


def _element_text(element: ET.Element) -> str:
    parts: list[str] = []
    for child in element.iter():
        if _local_name(child.tag) == "t" and child.text:
            parts.append(child.text)
    if not parts and element.text:
        parts.append(element.text)
    return "".join(parts)


_VML_SHAPE_TAGS = {"shape", "shapetype", "rect", "oval", "line", "imagedata", "group"}


def _accessible_names(element: ET.Element) -> list[str]:
    values: list[str] = []
    for child in element.iter():
        local = _local_name(child.tag)
        # VML (w:pict) shapes hold their alt text in an @alt attribute.
        if local in _VML_SHAPE_TAGS:
            value = _attr(child, "alt").strip()
            if value:
                values.append(value)
            continue
        if local not in {"docPr", "cNvPr"}:
            continue
        # Word's auto-generated @name ("Picture 1", "image1.png") is not an
        # accessible name, so only @descr (alt text) and @title count.
        for attr_name in ("descr", "title"):
            value = _attr(child, attr_name).strip()
            if value:
                values.append(value)
    return values


def _is_decorative(element: ET.Element) -> bool:
    for child in element.iter():
        if "decorative" not in _local_name(child.tag).lower():
            continue
        for value in child.attrib.values():
            if str(value).strip().lower() in {"1", "true"}:
                return True
        if not child.attrib:
            return True
    return False


def _element_has_image_reference(
    element: ET.Element, rels: dict[str, _Relationship]
) -> bool:
    for child in element.iter():
        local = _local_name(child.tag)
        if local == "blip":
            rel_id = _attr(child, "embed") or _attr(child, "link")
            rel = rels.get(rel_id)
            if rel is None:
                return True
            target = rel.target.lower()
            return (
                "/media/" in target
                or Path(target).suffix.lower() in _IMAGE_EXTENSIONS
                or "image" in rel.rel_type.lower()
            )
        if local == "imagedata":
            return True
    return False


def _element_has_non_image_object(element: ET.Element) -> bool:
    for child in element.iter():
        local = _local_name(child.tag)
        if local in {"oleObject", "object", "chart", "diagram"}:
            return True
    return False


def _is_placeholder_alt(alt: str, rels: dict[str, _Relationship]) -> bool:
    normalized = _normalize_text(alt)
    if normalized in _PLACEHOLDER_ALT:
        return True
    alt_lower = alt.strip().lower()
    if Path(alt_lower).suffix in _IMAGE_EXTENSIONS:
        return True
    for rel in rels.values():
        target_name = Path(rel.target).name.lower()
        if target_name and alt_lower == target_name:
            return True
    return False


def _normalize_text(value: str) -> str:
    return re.sub(r"[^\w\s]", "", re.sub(r"\s+", " ", value).strip().lower())


def _hyperlink_target_from_instruction(instruction: str) -> str:
    match = re.search(r'HYPERLINK\s+"([^"]+)"', instruction or "", re.IGNORECASE)
    return match.group(1) if match else ""


@dataclass
class _FieldFrame:
    """One `fldChar` begin/separate/end field while walking a paragraph."""

    instruction: list[str] = field(default_factory=list)
    visible: list[str] = field(default_factory=list)
    in_result: bool = False


def _field_hyperlinks(paragraph: ET.Element) -> list[tuple[str, str]]:
    """Return (visible text, target) for HYPERLINK fields in a paragraph.

    Word writes these as a run sequence rather than a `w:hyperlink` element:
    a `begin` fldChar, one or more `instrText` runs holding the URL, a
    `separate` fldChar, the runs the reader actually sees, then an `end`
    fldChar. Walking the runs in document order keeps each field's visible
    text separate, so a paragraph holding two links (or a link inside a
    longer sentence) does not attribute the whole paragraph to every link.
    """
    links: list[tuple[str, str]] = []
    stack: list[_FieldFrame] = []
    for run in _descendants(paragraph, "r"):
        fld_char = _first_child(run, "fldChar")
        if fld_char is not None:
            char_type = _attr(fld_char, "fldCharType")
            if char_type == "begin":
                stack.append(_FieldFrame())
            elif char_type == "separate":
                if stack:
                    stack[-1].in_result = True
            elif char_type == "end" and stack:
                frame = stack.pop()
                visible = "".join(frame.visible).strip()
                target = _hyperlink_target_from_instruction("".join(frame.instruction))
                if target:
                    links.append((visible, target))
                # A nested field's result is part of the enclosing field's text.
                if stack and stack[-1].in_result:
                    stack[-1].visible.append(visible)
            continue
        if not stack:
            continue
        frame = stack[-1]
        for instr in _descendants(run, "instrText"):
            frame.instruction.append(instr.text or "")
        if frame.in_result:
            frame.visible.append(_run_visible_text(run))
    return links


def _run_visible_text(run: ET.Element) -> str:
    return "".join(text.text or "" for text in _descendants(run, "t"))


def _is_merged_cell(cell: ET.Element) -> bool:
    """True when this cell is horizontally or vertically merged.

    Reads only the cell's own `tcPr`; descending would pick up the properties
    of a nested table's cells and blame them on the outer table.
    """
    cell_props = _first_child(cell, "tcPr")
    if cell_props is None:
        return False
    if _first_child(cell_props, "vMerge") is not None:
        return True
    return _grid_span(cell_props) > 1


def _grid_span(cell_props: ET.Element) -> int:
    grid_span = _first_child(cell_props, "gridSpan")
    value = _parse_int(_attr(grid_span, "val")) if grid_span is not None else None
    return value or 1


def _heading_level_from_outline(value: str) -> Optional[int]:
    """Map a `w:outlineLvl` value to a 1-based heading level.

    Values 0-8 are heading levels 1-9. Word writes 9 to mean "body text",
    which explicitly clears any outline level, so it is not a heading.
    """
    level = _parse_int(value)
    if level is None or not 0 <= level <= 8:
        return None
    return level + 1


def _is_toggle_on(element: Optional[ET.Element]) -> bool:
    """True when an OOXML toggle property (w:b, w:i, ...) is on.

    A bare element means on; `w:val` of 0/false/off explicitly turns it off.
    """
    if element is None:
        return False
    value = _attr(element, "val").strip().lower()
    if not value:
        return True
    return value not in {"0", "false", "off"}


def _parse_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _trailing_int(value: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*$", value or "")
    if not match:
        return None
    return int(match.group(1))


def _run_style_info(run_props: Optional[ET.Element], style_id: str) -> _StyleInfo:
    if run_props is None:
        return _StyleInfo(style_id=style_id)
    size_el = _first_child(run_props, "sz")
    return _StyleInfo(
        style_id=style_id,
        color=_run_color(run_props),
        size_half_points=(
            _parse_int(_attr(size_el, "val")) if size_el is not None else None
        ),
        bold=_is_toggle_on(_first_child(run_props, "b")),
    )


def _run_color(run_props: Optional[ET.Element]) -> Optional[str]:
    color_el = _first_child(run_props, "color")
    if color_el is None:
        return None
    value = _attr(color_el, "val").strip()
    if not value or value.lower() == "auto":
        return None
    return _normalize_hex(value)


def _shading_fill(props: Optional[ET.Element]) -> Optional[str]:
    shd = _first_child(props, "shd")
    if shd is None:
        return None
    fill = _attr(shd, "fill").strip()
    if not fill or fill.lower() in {"auto", "none"}:
        return None
    return _normalize_hex(fill)


def _highlight_fill(run_props: Optional[ET.Element]) -> Optional[str]:
    highlight = _first_child(run_props, "highlight")
    if highlight is None:
        return None
    return _HIGHLIGHT_COLORS.get(_attr(highlight, "val"))


def _normalize_hex(value: str) -> Optional[str]:
    value = value.strip().lstrip("#")
    if len(value) == 3 and re.fullmatch(r"[0-9a-fA-F]{3}", value):
        return "".join(ch * 2 for ch in value).upper()
    if len(value) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return value.upper()
    return None


def _rgb_from_hex(value: str) -> Optional[tuple[float, float, float]]:
    normalized = _normalize_hex(value)
    if normalized is None:
        return None
    return (
        int(normalized[0:2], 16) / 255.0,
        int(normalized[2:4], 16) / 255.0,
        int(normalized[4:6], 16) / 255.0,
    )


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def channel(value: float) -> float:
        if value <= _WCAG_SRGB_LINEAR_THRESHOLD:
            return value / _WCAG_SRGB_DIVISOR
        return ((value + _WCAG_SRGB_OFFSET) / _WCAG_SRGB_SCALE) ** _WCAG_SRGB_EXPONENT

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(
    fg: tuple[float, float, float], bg: tuple[float, float, float]
) -> float:
    first = _relative_luminance(fg)
    second = _relative_luminance(bg)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + _WCAG_CONTRAST_OFFSET) / (darker + _WCAG_CONTRAST_OFFSET)


def _is_large_text(size_half_points: Optional[int], bold: bool) -> bool:
    if size_half_points is None:
        return False
    points = size_half_points / 2
    return points >= 18 or (bold and points >= 14)


def _has_language_in_style_defaults(package: zipfile.ZipFile, names: set[str]) -> bool:
    if "word/styles.xml" not in names:
        return False
    try:
        root = ET.fromstring(package.read("word/styles.xml"))
    except (ET.ParseError, KeyError):
        return False
    doc_defaults = _first_descendant(root, "docDefaults")
    if doc_defaults is not None and _first_descendant(doc_defaults, "lang") is not None:
        return True
    for style in _descendants(root, "style"):
        if _first_descendant(style, "lang") is not None:
            return True
    return False
