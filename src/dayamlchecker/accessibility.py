from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Optional

TEXT_SECTION_KEYS = ("question", "subquestion", "under", "help", "note", "html")
FIELD_NON_LABEL_KEYS = {
    "code",
    "default",
    "default value",
    "hint",
    "help",
    "label",
    "datatype",
    "choices",
    "validation code",
    "show if",
    "hide if",
    "js show if",
    "js hide if",
    "enable if",
    "disable if",
    "js enable if",
    "js disable if",
    "required",
    "field",
    "__line__",
}
GENERIC_LINK_TEXT = {
    "click here",
    "here",
    "learn more",
    "read more",
    "haga clic aqui",
    "haga clic aquí",
    "clic aqui",
    "clic aquí",
    "aqui",
    "aquí",
}


@dataclass(frozen=True)
class AccessibilityFinding:
    rule_id: str
    message: str
    line_number: int


@dataclass(frozen=True)
class TextSection:
    location: str
    value: str
    key_line: int


_MARKDOWN_IMAGE_RE = re.compile(r"!\[(.*?)\]\((.*?)\)")
_FILE_TAG_RE = re.compile(
    r"\[FILE\s+([^,\]]+)(?:\s*,\s*([^,\]]+))?(?:\s*,\s*([^\]]+))?\]"
)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_MARKDOWN_HEADING_RE = re.compile(r"(?m)^\s*(#{1,6})\s+(.+?)\s*$")
_HTML_HEADING_RE = re.compile(
    r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL
)
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[(.*?)\]\((.*?)\)")
_HTML_LINK_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_CSS_RULE_RE = re.compile(r"(?s)([^{}]+)\{([^{}]+)\}")
_HEX_COLOR_RE = re.compile(r"^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$", re.IGNORECASE)
_RGB_COLOR_RE = re.compile(r"rgba?\(([^\)]+)\)", re.IGNORECASE)
_VAR_COLOR_RE = re.compile(
    r"var\((--[a-zA-Z0-9\-_]+)(?:\s*,\s*([^\)]+))?\)", re.IGNORECASE
)
_COMPONENT_SELECTORS = {
    "body text": ["body"],
    "navbar": [".navbar", ".nav-link", ".navbar-brand"],
    "dropdown menu": [".dropdown-menu", ".dropdown-item"],
    "buttons": [".btn"],
}


def find_accessibility_findings(
    *,
    doc: dict[str, Any],
    source_code: str,
    document_start_line: int,
    input_file: Optional[str] = None,
) -> list[AccessibilityFinding]:
    findings: list[AccessibilityFinding] = []
    findings.extend(_check_multifield_no_label_usage(doc, document_start_line))
    findings.extend(_check_combobox_usage(doc, source_code, document_start_line))
    findings.extend(_check_tagged_pdf_for_docx(doc, source_code, document_start_line))
    findings.extend(
        _check_theme_css_contrast(
            doc,
            source_code,
            document_start_line,
            input_file=input_file,
        )
    )
    for section in _iter_text_sections(doc, source_code):
        findings.extend(
            _check_missing_alt_text(section, source_code, document_start_line)
        )
        findings.extend(
            _check_empty_link_text(section, source_code, document_start_line)
        )
        findings.extend(
            _check_non_descriptive_link_text(section, source_code, document_start_line)
        )
        findings.extend(
            _check_markdown_heading_order(section, source_code, document_start_line)
        )
        findings.extend(
            _check_html_heading_order(section, source_code, document_start_line)
        )
    unique_findings: list[AccessibilityFinding] = []
    seen: set[tuple[str, str, int]] = set()
    for finding in findings:
        key = (finding.rule_id, finding.message, finding.line_number)
        if key in seen:
            continue
        seen.add(key)
        unique_findings.append(finding)
    return unique_findings


def _check_combobox_usage(
    doc: dict[str, Any], source_code: str, document_start_line: int
) -> list[AccessibilityFinding]:
    findings: list[AccessibilityFinding] = []
    top_level_combobox = doc.get("combobox")
    if top_level_combobox is not None:
        line_number = _absolute_line_number(
            source_code,
            document_start_line,
            _find_top_level_key_line(source_code, "combobox") or doc.get("__line__", 1),
            "combobox:",
        )
        findings.append(
            AccessibilityFinding(
                rule_id="combobox-not-accessible",
                message="Accessibility: screen uses `combobox`, which is not allowed for accessibility reasons",
                line_number=line_number,
            )
        )

    for field in _iter_fields(doc):
        datatype = str(field.get("datatype") or "").strip().lower()
        if datatype != "combobox":
            continue
        field_label = (
            _extract_field_label(field)
            or _extract_field_variable(field)
            or "<unknown field>"
        )
        findings.append(
            AccessibilityFinding(
                rule_id="combobox-not-accessible",
                message=(
                    "Accessibility: field uses `datatype: combobox`, which is not allowed for accessibility reasons: "
                    f"{field_label}"
                ),
                line_number=document_start_line
                + field.get("__line__", doc.get("__line__", 1))
                - 1,
            )
        )

    return findings


def _check_multifield_no_label_usage(
    doc: dict[str, Any], document_start_line: int
) -> list[AccessibilityFinding]:
    fields = _iter_fields(doc)
    if len(fields) <= 1:
        return []

    findings: list[AccessibilityFinding] = []
    for field in fields:
        field_line = (
            document_start_line + field.get("__line__", doc.get("__line__", 1)) - 1
        )
        no_label_value = field.get("no label")
        has_no_label = _is_truthy(no_label_value)
        explicit_label = str(field.get("label") or "")
        inferred_label = _extract_field_label(field)
        label_is_blank = "label" in field and not explicit_label.strip()
        missing_label = not inferred_label.strip()

        if not (has_no_label or label_is_blank or missing_label):
            continue

        field_name = _extract_field_variable(field) or "<unknown field>"
        findings.append(
            AccessibilityFinding(
                rule_id="no-label-on-multi-field-screen",
                message=(
                    "Accessibility: `no label` or empty/missing field label is only allowed on single-field screens; "
                    f"screen has {len(fields)} fields: {field_name}"
                ),
                line_number=field_line,
            )
        )
    return findings


def _check_tagged_pdf_for_docx(
    doc: dict[str, Any], source_code: str, document_start_line: int
) -> list[AccessibilityFinding]:
    attachments = doc.get("attachments")
    if isinstance(attachments, dict):
        attachments = [attachments]
    if not isinstance(attachments, list):
        return []

    features = doc.get("features")
    feature_tagged_pdf = False
    if isinstance(features, dict):
        feature_tagged_pdf = _is_truthy(features.get("tagged pdf"))

    findings: list[AccessibilityFinding] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        if not _attachment_uses_docx(attachment):
            continue
        if feature_tagged_pdf or _is_truthy(attachment.get("tagged pdf")):
            continue

        line_hint = _find_top_level_key_line(source_code, "attachments") or doc.get(
            "__line__", 1
        )
        line_number = _absolute_line_number(
            source_code,
            document_start_line,
            line_hint,
            "attachments:",
        )
        findings.append(
            AccessibilityFinding(
                rule_id="tagged-pdf-not-enabled",
                message=(
                    "Warning: Accessibility: DOCX attachment detected without `tagged pdf: True`; "
                    "set it on `features` or the attachment to improve generated PDF accessibility"
                ),
                line_number=line_number,
            )
        )
    return findings


def _check_theme_css_contrast(
    doc: dict[str, Any],
    source_code: str,
    document_start_line: int,
    *,
    input_file: Optional[str] = None,
) -> list[AccessibilityFinding]:
    features = doc.get("features")
    if not isinstance(features, dict):
        return []

    theme_value = str(features.get("bootstrap theme") or "").strip()
    if not theme_value:
        return []
    line_hint = _find_top_level_key_line(source_code, "features") or doc.get(
        "__line__", 1
    )
    line_number = _absolute_line_number(
        source_code,
        document_start_line,
        line_hint,
        "bootstrap theme",
    )

    css_content = _load_bootstrap_theme_css(theme_value, input_file=input_file)
    if not css_content:
        return []

    selector_props, variables = _parse_css_rules(css_content)
    findings: list[AccessibilityFinding] = []
    for component, patterns in _COMPONENT_SELECTORS.items():
        pair = _best_component_color_pair(selector_props, variables, patterns)
        if pair is None:
            continue
        fg, bg = pair
        ratio = _contrast_ratio(fg, bg)
        if ratio >= 4.5:
            continue
        findings.append(
            AccessibilityFinding(
                rule_id="theme-contrast-too-low",
                message=(
                    "Accessibility: bootstrap theme CSS has low contrast for "
                    f"{component} (ratio {ratio:.2f}:1, expected at least 4.5:1)"
                ),
                line_number=line_number,
            )
        )
    return findings


def _iter_text_sections(doc: dict[str, Any], source_code: str) -> list[TextSection]:
    sections: list[TextSection] = []
    for key in TEXT_SECTION_KEYS:
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            sections.append(
                TextSection(
                    location=key,
                    value=value,
                    key_line=_find_top_level_key_line(source_code, key)
                    or doc.get("__line__", 1),
                )
            )
        elif isinstance(value, dict):
            for subkey in ("content", "label"):
                subvalue = value.get(subkey)
                if isinstance(subvalue, str) and subvalue.strip():
                    sections.append(
                        TextSection(
                            location=f"{key}.{subkey}",
                            value=subvalue,
                            key_line=_find_top_level_key_line(source_code, key)
                            or doc.get("__line__", 1),
                        )
                    )
    return sections


def _check_missing_alt_text(
    section: TextSection, source_code: str, document_start_line: int
) -> list[AccessibilityFinding]:
    findings: list[AccessibilityFinding] = []
    for alt_text, image_target in _MARKDOWN_IMAGE_RE.findall(section.value):
        if alt_text.strip():
            continue
        snippet = f"![{alt_text}]({image_target})"
        findings.append(
            AccessibilityFinding(
                rule_id="image-missing-alt-text",
                message=(
                    f"Accessibility: markdown image in {section.location} is missing alt text: {snippet}"
                ),
                line_number=_absolute_line_number(
                    source_code,
                    document_start_line,
                    section.key_line,
                    snippet,
                ),
            )
        )

    for file_target, width_value, alt_text in _FILE_TAG_RE.findall(section.value):
        if str(alt_text).strip():
            continue
        snippet = f"[FILE {file_target}, {width_value}]"
        findings.append(
            AccessibilityFinding(
                rule_id="image-missing-alt-text",
                message=(
                    f"Accessibility: [FILE ...] image in {section.location} is missing alt text: {snippet}"
                ),
                line_number=_absolute_line_number(
                    source_code,
                    document_start_line,
                    section.key_line,
                    f"[FILE {file_target}",
                ),
            )
        )

    for img_tag in _IMG_TAG_RE.findall(section.value):
        alt_match = re.search(r"\balt\s*=\s*([\"'])(.*?)\1", img_tag, re.IGNORECASE)
        if alt_match and alt_match.group(2).strip():
            continue
        findings.append(
            AccessibilityFinding(
                rule_id="image-missing-alt-text",
                message=(
                    f"Accessibility: HTML image in {section.location} is missing alt text: {img_tag.strip()}"
                ),
                line_number=_absolute_line_number(
                    source_code,
                    document_start_line,
                    section.key_line,
                    img_tag.strip(),
                ),
            )
        )
    return findings


def _check_markdown_heading_order(
    section: TextSection, source_code: str, document_start_line: int
) -> list[AccessibilityFinding]:
    findings: list[AccessibilityFinding] = []
    matches = list(_MARKDOWN_HEADING_RE.finditer(section.value))
    for index in range(1, len(matches)):
        previous_level = len(matches[index - 1].group(1))
        current_level = len(matches[index].group(1))
        if current_level <= previous_level + 1:
            continue
        line_text = matches[index].group(0).strip()
        findings.append(
            AccessibilityFinding(
                rule_id="markdown-heading-level-skip",
                message=(
                    "Accessibility: markdown heading levels skip "
                    f"from H{previous_level} to H{current_level} in {section.location}: {line_text}"
                ),
                line_number=_absolute_line_number(
                    source_code,
                    document_start_line,
                    section.key_line,
                    line_text,
                ),
            )
        )
        break
    return findings


def _check_html_heading_order(
    section: TextSection, source_code: str, document_start_line: int
) -> list[AccessibilityFinding]:
    findings: list[AccessibilityFinding] = []
    matches = list(_HTML_HEADING_RE.finditer(section.value))
    for index in range(1, len(matches)):
        previous_level = int(matches[index - 1].group(1))
        current_level = int(matches[index].group(1))
        if current_level <= previous_level + 1:
            continue
        snippet = re.sub(r"\s+", " ", matches[index].group(0)).strip()
        findings.append(
            AccessibilityFinding(
                rule_id="html-heading-level-skip",
                message=(
                    "Accessibility: HTML heading levels skip "
                    f"from H{previous_level} to H{current_level} in {section.location}: {snippet}"
                ),
                line_number=_absolute_line_number(
                    source_code,
                    document_start_line,
                    section.key_line,
                    snippet,
                ),
            )
        )
        break
    return findings


def _check_empty_link_text(
    section: TextSection, source_code: str, document_start_line: int
) -> list[AccessibilityFinding]:
    findings: list[AccessibilityFinding] = []
    for link in _extract_links_from_text(section.value):
        visible_text = _normalize_human_text(link["text"])
        if visible_text:
            continue
        if link["kind"] == "html" and (
            link["aria_label"].strip() or link["title"].strip()
        ):
            continue
        findings.append(
            AccessibilityFinding(
                rule_id="empty-link-text",
                message=(
                    f"Accessibility: link in {section.location} has no accessible text: {link['snippet']}"
                ),
                line_number=_absolute_line_number(
                    source_code,
                    document_start_line,
                    section.key_line,
                    link["snippet"],
                ),
            )
        )
    return findings


def _check_non_descriptive_link_text(
    section: TextSection, source_code: str, document_start_line: int
) -> list[AccessibilityFinding]:
    findings: list[AccessibilityFinding] = []
    for link in _extract_links_from_text(section.value):
        normalized = _normalize_human_text(link["text"])
        if not normalized or normalized not in GENERIC_LINK_TEXT:
            continue
        findings.append(
            AccessibilityFinding(
                rule_id="non-descriptive-link-text",
                message=(
                    f"Accessibility: link text in {section.location} is too generic: {link['text'].strip() or link['snippet']}"
                ),
                line_number=_absolute_line_number(
                    source_code,
                    document_start_line,
                    section.key_line,
                    link["snippet"],
                ),
            )
        )
    return findings


def _find_top_level_key_line(source_code: str, key: str) -> Optional[int]:
    key_re = re.compile(rf"^{re.escape(key)}\s*:", re.MULTILINE)
    match = key_re.search(source_code)
    if not match:
        return None
    return source_code.count("\n", 0, match.start()) + 1


def _absolute_line_number(
    source_code: str, document_start_line: int, section_key_line: int, snippet: str
) -> int:
    relative_line = _find_snippet_line(
        source_code, snippet, start_line=section_key_line
    )
    if relative_line is None:
        relative_line = section_key_line
    return document_start_line + relative_line - 1


def _find_snippet_line(
    source_code: str, snippet: str, *, start_line: int = 1
) -> Optional[int]:
    normalized_snippet = re.sub(r"\s+", " ", snippet).strip()
    if not normalized_snippet:
        return None
    lines = source_code.splitlines()
    start_index = max(start_line - 1, 0)
    for index in range(start_index, len(lines)):
        normalized_line = re.sub(r"\s+", " ", lines[index]).strip()
        if normalized_snippet in normalized_line:
            return index + 1
    return None


def _iter_fields(doc: dict[str, Any]) -> list[dict[str, Any]]:
    fields = doc.get("fields")
    if isinstance(fields, dict):
        fields = [fields]
    if not isinstance(fields, list):
        return []
    return [field for field in fields if isinstance(field, dict)]


def _extract_field_variable(field: dict[str, Any]) -> str:
    explicit = str(field.get("field") or "").strip()
    if explicit:
        return explicit
    for key, value in field.items():
        if key in FIELD_NON_LABEL_KEYS:
            continue
        if isinstance(value, str):
            return value.strip()
    return ""


def _extract_field_label(field: dict[str, Any]) -> str:
    explicit = str(field.get("label") or "").strip()
    if explicit:
        return explicit
    for key in field.keys():
        key_text = str(key).strip()
        if key_text and key_text not in FIELD_NON_LABEL_KEYS:
            return key_text
    return ""


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "on"}
    return False


def _attachment_uses_docx(attachment: dict[str, Any]) -> bool:
    for key, value in attachment.items():
        key_text = str(key or "").strip().lower()
        value_text = str(value or "").strip().lower()
        if "docx" in key_text:
            return True
        if key_text in {"template file", "template"} and value_text.endswith(".docx"):
            return True
        if value_text.endswith(".docx"):
            return True
    return False


def _load_bootstrap_theme_css(
    theme_value: str, *, input_file: Optional[str]
) -> Optional[str]:
    path = theme_value.strip().strip('"').strip("'")
    if not path or path.startswith(("http://", "https://")):
        return None

    candidates: list[Path] = []
    theme_path = Path(path)
    if theme_path.is_absolute():
        candidates.append(theme_path)
    else:
        candidates.append(Path.cwd() / theme_path)
        if input_file and input_file != "<string input>":
            interview_parent = Path(input_file).resolve().parent
            candidates.append(interview_parent / theme_path)

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return None


def _parse_css_rules(
    css_content: str,
) -> tuple[list[tuple[list[str], dict[str, str]]], dict[str, str]]:
    selector_props: list[tuple[list[str], dict[str, str]]] = []
    variables: dict[str, str] = {}
    for selector_group, body in _CSS_RULE_RE.findall(css_content):
        selectors = [s.strip().lower() for s in selector_group.split(",") if s.strip()]
        declarations = _parse_css_declarations(body)
        if not declarations:
            continue
        for key, value in declarations.items():
            if key.startswith("--"):
                variables[key] = value
        selector_props.append((selectors, declarations))
    return selector_props, variables


def _parse_css_declarations(body: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for raw in body.split(";"):
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            declarations[key] = value
    return declarations


def _best_component_color_pair(
    selector_props: list[tuple[list[str], dict[str, str]]],
    variables: dict[str, str],
    selector_patterns: list[str],
) -> Optional[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    fg: Optional[tuple[float, float, float]] = None
    bg: Optional[tuple[float, float, float]] = None

    for selectors, props in selector_props:
        selector_text = " ".join(selectors)
        if not any(pattern in selector_text for pattern in selector_patterns):
            continue
        color_value = _resolve_css_color(props.get("color"), variables)
        bg_value = _resolve_css_color(
            props.get("background-color") or props.get("background"),
            variables,
        )

        if color_value and bg_value:
            return (color_value, bg_value)
        if color_value and fg is None:
            fg = color_value
        if bg_value and bg is None:
            bg = bg_value

    if fg and bg:
        return (fg, bg)
    return None


def _resolve_css_color(
    value: Optional[str], variables: dict[str, str]
) -> Optional[tuple[float, float, float]]:
    if not value:
        return None
    color_text = value.strip().lower()

    var_match = _VAR_COLOR_RE.search(color_text)
    if var_match:
        var_name = var_match.group(1)
        fallback = (var_match.group(2) or "").strip()
        replacement = variables.get(var_name, fallback)
        if replacement:
            return _resolve_css_color(replacement, variables)

    token = _extract_color_token(color_text)
    if not token:
        return None

    hex_match = _HEX_COLOR_RE.match(token)
    if hex_match:
        code = hex_match.group(1)
        if len(code) == 3:
            r = int(code[0] * 2, 16)
            g = int(code[1] * 2, 16)
            b = int(code[2] * 2, 16)
        else:
            r = int(code[0:2], 16)
            g = int(code[2:4], 16)
            b = int(code[4:6], 16)
        return (r / 255.0, g / 255.0, b / 255.0)

    rgb_match = _RGB_COLOR_RE.search(token)
    if rgb_match:
        parts = [p.strip() for p in rgb_match.group(1).split(",")]
        if len(parts) < 3:
            return None
        try:
            r = _parse_rgb_channel(parts[0])
            g = _parse_rgb_channel(parts[1])
            b = _parse_rgb_channel(parts[2])
        except ValueError:
            return None
        return (r, g, b)

    if token in {"black", "#000", "#000000"}:
        return (0.0, 0.0, 0.0)
    if token in {"white", "#fff", "#ffffff"}:
        return (1.0, 1.0, 1.0)
    return None


def _extract_color_token(value: str) -> Optional[str]:
    if _HEX_COLOR_RE.match(value):
        return value
    m = _RGB_COLOR_RE.search(value)
    if m:
        return m.group(0)
    if value.startswith("var("):
        return value

    for token in re.split(r"\s+", value):
        cleaned = token.strip().strip(",")
        if _HEX_COLOR_RE.match(cleaned):
            return cleaned
        m = _RGB_COLOR_RE.search(cleaned)
        if m:
            return m.group(0)
        if cleaned in {"black", "white"}:
            return cleaned
    return None


def _parse_rgb_channel(raw: str) -> float:
    raw = raw.strip()
    if raw.endswith("%"):
        value = float(raw[:-1]) / 100.0
        return max(0.0, min(1.0, value))
    value = float(raw)
    if value > 1.0:
        value = value / 255.0
    return max(0.0, min(1.0, value))


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def _channel(c: float) -> float:
        if c <= 0.03928:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast_ratio(
    fg: tuple[float, float, float], bg: tuple[float, float, float]
) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _normalize_human_text(value: str) -> str:
    plain_text = re.sub(r"<[^>]+>", " ", value or "")
    plain_text = re.sub(r"\s+", " ", plain_text).strip().lower()
    return re.sub(r"[^\w\sáéíóúüñ]", "", plain_text)


def _extract_links_from_text(text: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for link_text, target in _MARKDOWN_LINK_RE.findall(text):
        links.append(
            {
                "kind": "markdown",
                "text": str(link_text),
                "target": str(target),
                "aria_label": "",
                "title": "",
                "snippet": f"[{link_text}]({target})",
            }
        )
    for attrs, inner in _HTML_LINK_RE.findall(text):
        href_match = re.search(r"\bhref\s*=\s*([\"'])(.*?)\1", attrs, re.IGNORECASE)
        aria_label_match = re.search(
            r"\baria-label\s*=\s*([\"'])(.*?)\1", attrs, re.IGNORECASE
        )
        title_match = re.search(r"\btitle\s*=\s*([\"'])(.*?)\1", attrs, re.IGNORECASE)
        snippet = re.sub(r"\s+", " ", f"<a{attrs}>{inner}</a>").strip()
        links.append(
            {
                "kind": "html",
                "text": str(inner),
                "target": str(href_match.group(2) if href_match else ""),
                "aria_label": str(
                    aria_label_match.group(2) if aria_label_match else ""
                ),
                "title": str(title_match.group(2) if title_match else ""),
                "snippet": snippet,
            }
        )
    return links
