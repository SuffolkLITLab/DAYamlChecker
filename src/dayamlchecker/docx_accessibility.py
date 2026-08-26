from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import zipfile
from typing import Optional
import xml.etree.ElementTree as ET

ERROR = "error"
WARNING = "warning"
TIP = "tip"

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


@dataclass(frozen=True)
class DocxAccessibilityFinding:
    rule_id: str
    severity: str
    message: str
    location: str = "document"
    wcag: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocxAccessibilityOptions:
    errors_as_warnings: bool = False
    table_merged_cells_severity: str = WARNING
    document_language_missing_severity: str = ERROR
    document_title_missing_severity: str = WARNING
    rules: dict[str, str] = field(default_factory=dict)

    def severity(self, rule_id: str, default: str) -> str:
        severity = self.rules.get(rule_id, default)
        if severity not in {ERROR, WARNING, TIP, "ignore"}:
            severity = default
        if self.errors_as_warnings and severity == ERROR:
            return WARNING
        return severity


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
) -> list[DocxAccessibilityFinding]:
    options = options or DocxAccessibilityOptions()
    path = Path(path)

    try:
        with zipfile.ZipFile(path) as package:
            names = set(package.namelist())
            if "word/document.xml" not in names:
                return [
                    _finding(
                        options,
                        "docx-unreadable",
                        ERROR,
                        "DOCX is missing word/document.xml",
                        "package",
                    )
                ]
            context = _DocxContext(package, names, path)
            return context.check(options)
    except (OSError, zipfile.BadZipFile):
        return [
            _finding(
                options,
                "docx-unreadable",
                ERROR,
                "File is not a valid DOCX ZIP package",
                "package",
            )
        ]


def collect_docx_files(
    paths: list[Path], include_default_ignores: bool = True
) -> list[Path]:
    ignored = {".hg", ".mypy_cache", ".pytest_cache", "__pycache__"}
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
        self.relationships: dict[str, dict[str, _Relationship]] = {}
        self.styles: dict[str, _StyleInfo] = {}
        self.default_run_style = _StyleInfo(style_id="", is_default_run=True)

    def check(
        self, options: DocxAccessibilityOptions
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
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
                            "heading-empty",
                            WARNING,
                            "Empty paragraph uses a heading style",
                            part_name,
                            ("1.3.1", "2.4.6"),
                        )
                    )
                if (
                    paragraph_text.strip().isupper()
                    and len(paragraph_text.strip()) >= 8
                ):
                    findings.append(
                        _finding(
                            options,
                            "all-caps-heading",
                            TIP,
                            "Heading is all caps; review readability",
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
        return _unique_findings(
            [finding for finding in findings if finding.severity != "ignore"]
        )

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
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
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
                    "document-title-missing",
                    options.document_title_missing_severity,
                    "Document title metadata is missing",
                    "docProps/core.xml",
                    ("2.4.2",),
                )
            )
        elif (
            title.strip().lower() == filename_stem
            or title.strip().lower() in _GENERIC_TITLES
        ):
            findings.append(
                _finding(
                    options,
                    "document-title-missing",
                    options.document_title_missing_severity,
                    "Document title metadata is generic or repeats the filename",
                    "docProps/core.xml",
                    ("2.4.2",),
                )
            )
        if filename_stem in _GENERIC_FILENAMES:
            findings.append(
                _finding(
                    options,
                    "filename-not-descriptive",
                    TIP,
                    "File name is generic; use a descriptive file name",
                    "package",
                )
            )
        return findings

    def _check_document_language(
        self, options: DocxAccessibilityOptions
    ) -> list[DocxAccessibilityFinding]:
        if self.default_run_style and _has_language_in_style_defaults(
            self.package, self.names
        ):
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
                "document-language-missing",
                options.document_language_missing_severity,
                "No default document language was detected",
                "word/styles.xml",
                ("3.1.1",),
            )
        ]

    def _check_drawings_and_objects(
        self,
        part_name: str,
        root: ET.Element,
        options: DocxAccessibilityOptions,
        alt_texts: list[str],
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
        candidates = list(_descendants(root, "drawing")) + list(
            _descendants(root, "pict")
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
                        "decorative-image-has-alt",
                        WARNING,
                        "Image is marked decorative but also has alt text or a title",
                        part_name,
                        ("1.1.1",),
                    )
                )

            if is_image:
                if not has_accessible_name and not decorative:
                    findings.append(
                        _finding(
                            options,
                            "image-alt-missing",
                            ERROR,
                            "Image has no alt text and is not marked decorative",
                            part_name,
                            ("1.1.1",),
                        )
                    )
                for alt in alt_values:
                    if _is_placeholder_alt(alt, rels):
                        findings.append(
                            _finding(
                                options,
                                "image-alt-placeholder",
                                WARNING,
                                f'Image alt text looks like a placeholder: "{alt}"',
                                part_name,
                                ("1.1.1",),
                            )
                        )
                continue

            if _element_has_non_image_object(element) and not has_accessible_name:
                findings.append(
                    _finding(
                        options,
                        "object-alt-missing",
                        ERROR,
                        "Non-image drawing or object has no accessible name",
                        part_name,
                        ("1.1.1",),
                    )
                )
        return findings

    def _check_hyperlinks(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
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
            targets = [
                _hyperlink_target_from_instruction(_element_text(instr))
                for instr in _descendants(paragraph, "instrText")
            ]
            for target in [target for target in targets if target]:
                visible = "".join(
                    _element_text(text_element)
                    for text_element in _descendants(paragraph, "t")
                ).strip()
                links.append((visible, target))

        for visible, target in links:
            normalized = _normalize_text(visible)
            if not normalized:
                findings.append(
                    _finding(
                        options,
                        "hyperlink-empty",
                        ERROR,
                        f"Hyperlink to {target} has no visible text",
                        part_name,
                        ("2.4.4",),
                    )
                )
                continue
            text_to_targets.setdefault(normalized, set()).add(target)
            target_to_texts.setdefault(target, set()).add(normalized)
            if _RAW_URL_RE.match(visible.strip()):
                findings.append(
                    _finding(
                        options,
                        "link-raw-url",
                        WARNING,
                        f'Link text is a raw URL: "{visible.strip()}"',
                        part_name,
                        ("2.4.4",),
                    )
                )
            if normalized in _AMBIGUOUS_LINK_TEXT:
                findings.append(
                    _finding(
                        options,
                        "link-ambiguous",
                        WARNING,
                        f'Link text is ambiguous: "{visible.strip()}"',
                        part_name,
                        ("2.4.4",),
                    )
                )

        for text, targets in text_to_targets.items():
            if len(targets) > 1:
                findings.append(
                    _finding(
                        options,
                        "link-ambiguous",
                        WARNING,
                        f'Link text "{text}" points to multiple URLs',
                        part_name,
                        ("2.4.4",),
                    )
                )
        for target, texts in target_to_texts.items():
            if len(texts) > 1:
                findings.append(
                    _finding(
                        options,
                        "link-same-url-different-text",
                        TIP,
                        f"Same URL has multiple link texts: {target}",
                        part_name,
                        ("2.4.4",),
                    )
                )
        return findings

    def _check_tables(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
        for table in _descendants(root, "tbl"):
            rows = list(_children(table, "tr"))
            cells = list(_descendants(table, "tc"))
            has_nested_table = any(
                _first_descendant(cell, "tbl") is not None for cell in cells
            )
            has_header = any(
                _first_descendant(row, "tblHeader") is not None for row in rows[:1]
            )
            has_merged = any(
                _grid_span(cell) > 1 or _first_descendant(cell, "vMerge") is not None
                for cell in cells
            )
            if has_merged:
                findings.append(
                    _finding(
                        options,
                        "table-merged-cells",
                        options.table_merged_cells_severity,
                        "Table contains merged or split cells",
                        part_name,
                        ("1.3.1",),
                    )
                )
            if has_nested_table:
                findings.append(
                    _finding(
                        options,
                        "table-layout-suspected",
                        WARNING,
                        "Nested table found; verify it is not being used for layout",
                        part_name,
                        ("1.3.1",),
                    )
                )
            if len(rows) >= 2 and len(cells) >= 4 and not has_header:
                findings.append(
                    _finding(
                        options,
                        "table-no-header-row",
                        WARNING,
                        "Table has no obvious header row marker",
                        part_name,
                        ("1.3.1",),
                    )
                )
            empty_cells = [cell for cell in cells if not _element_text(cell).strip()]
            if len(cells) >= 4 and len(empty_cells) / max(len(cells), 1) >= 0.5:
                findings.append(
                    _finding(
                        options,
                        "table-layout-suspected",
                        WARNING,
                        "Table has many empty cells and may be used for layout",
                        part_name,
                        ("1.3.1", "1.3.2"),
                    )
                )
        return findings

    def _check_reading_order_risks(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
        if _first_descendant(root, "anchor") is not None:
            findings.append(
                _finding(
                    options,
                    "floating-object-detected",
                    WARNING,
                    "Floating object detected; verify reading order in Word",
                    part_name,
                    ("1.3.2",),
                )
            )
        risky_names = {
            "txbxContent": "text-box-detected",
            "textbox": "text-box-detected",
            "chart": "floating-object-detected",
            "diagram": "floating-object-detected",
            "smartArt": "floating-object-detected",
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
                _finding(options, rule_id, WARNING, message, part_name, ("1.3.2",))
            )
        return findings

    def _check_contrast(
        self, part_name: str, root: ET.Element, options: DocxAccessibilityOptions
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
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
    ) -> list[DocxAccessibilityFinding]:
        paragraph_bg = _shading_fill(_first_child(paragraph, "pPr")) or inherited_bg
        findings: list[DocxAccessibilityFinding] = []
        for run in _children(paragraph, "r"):
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
                        "contrast-explicit-fail",
                        ERROR,
                        (
                            "Explicit text and background colors are below WCAG AA "
                            f"contrast threshold ({ratio:.2f}:1, expected {threshold:.1f}:1)"
                        ),
                        part_name,
                        ("1.4.3",),
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
            value = _parse_int(_attr(outline, "val"))
            return value + 1 if value is not None else None
        style_el = _first_child(p_props, "pStyle")
        style_id = _attr(style_el, "val") if style_el is not None else ""
        if not style_id:
            return None
        style = self._resolve_style(style_id)
        if style.outline_level is not None:
            return style.outline_level + 1
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
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
        if not heading_levels and text_length >= 400:
            findings.append(
                _finding(
                    options,
                    "heading-none",
                    WARNING,
                    "No built-in heading styles were detected",
                    "word/document.xml",
                    ("1.3.1", "2.4.6"),
                )
            )
            return findings
        if heading_levels and heading_levels[0][0] > 1:
            findings.append(
                _finding(
                    options,
                    "heading-order-starts-too-low",
                    WARNING,
                    f"Heading structure starts at level {heading_levels[0][0]}",
                    "word/document.xml",
                    ("1.3.1", "2.4.6"),
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
                    "heading-skipped-level",
                    WARNING,
                    f"Heading levels skip from H{previous_level} to H{current_level}: {text.strip()}",
                    "word/document.xml",
                    ("1.3.1", "2.4.6"),
                )
            )
            break
        return findings

    def _check_document_text_risks(
        self, document_text: str, options: DocxAccessibilityOptions
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
        word_count = len(document_text.split())
        image_refs = 0
        for part_name in self.names:
            if part_name.startswith("word/media/"):
                image_refs += 1
        if image_refs > 0 and word_count < 20:
            findings.append(
                _finding(
                    options,
                    "image-only-document",
                    WARNING,
                    "Document has very little real text and may be scanned or image-based",
                    "word/document.xml",
                    ("1.1.1", "1.3.1"),
                )
            )
        lowered = document_text.lower()
        if "color" in lowered and _COLOR_ONLY_RE.search(lowered):
            findings.append(
                _finding(
                    options,
                    "color-only-risk",
                    WARNING,
                    "Text may use color as the only cue",
                    "word/document.xml",
                    ("1.4.1",),
                )
            )
        return findings

    def _check_tips(
        self,
        alt_texts: list[str],
        empty_paragraphs: int,
        manual_numbering_count: int,
        options: DocxAccessibilityOptions,
    ) -> list[DocxAccessibilityFinding]:
        findings: list[DocxAccessibilityFinding] = []
        for alt in alt_texts:
            if len(alt.split()) >= 30 or len(alt) >= 180:
                findings.append(
                    _finding(
                        options,
                        "long-alt-text",
                        TIP,
                        "Alt text is very long; consider moving detail into nearby body text",
                        "word/document.xml",
                        ("1.1.1",),
                    )
                )
        if empty_paragraphs >= 5:
            findings.append(
                _finding(
                    options,
                    "many-empty-paragraphs",
                    TIP,
                    "Document contains many empty paragraphs used for spacing",
                    "word/document.xml",
                )
            )
        if manual_numbering_count >= 3:
            findings.append(
                _finding(
                    options,
                    "manual-numbering-detected",
                    TIP,
                    "Text looks like manual list numbering instead of Word lists",
                    "word/document.xml",
                    ("1.3.1",),
                )
            )
        return findings


def _finding(
    options: DocxAccessibilityOptions,
    rule_id: str,
    default_severity: str,
    message: str,
    location: str,
    wcag: tuple[str, ...] = (),
) -> DocxAccessibilityFinding:
    return DocxAccessibilityFinding(
        rule_id=rule_id,
        severity=options.severity(rule_id, default_severity),
        message=message,
        location=location,
        wcag=wcag,
    )


def _unique_findings(
    findings: list[DocxAccessibilityFinding],
) -> list[DocxAccessibilityFinding]:
    unique: list[DocxAccessibilityFinding] = []
    seen: set[tuple[str, str, str, str]] = set()
    for finding in findings:
        key = (finding.rule_id, finding.severity, finding.message, finding.location)
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


def _accessible_names(element: ET.Element) -> list[str]:
    values: list[str] = []
    for child in element.iter():
        if _local_name(child.tag) not in {"docPr", "cNvPr"}:
            continue
        for attr_name in ("descr", "title", "name"):
            value = _attr(child, attr_name).strip()
            if value and attr_name != "name":
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


def _grid_span(cell: ET.Element) -> int:
    grid_span = _first_descendant(cell, "gridSpan")
    value = _parse_int(_attr(grid_span, "val")) if grid_span is not None else None
    return value or 1


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
        bold=_first_child(run_props, "b") is not None,
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
    value = _normalize_hex(value)
    if value is None:
        return None
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
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
