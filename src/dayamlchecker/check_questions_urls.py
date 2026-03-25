#!/usr/bin/env python3
"""Check absolute URLs in docassemble question/template files and fail on HTTP 404 responses."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import requests
from docx2python import docx2python
from linkify_it import LinkifyIt  # type: ignore[attr-defined,import-untyped]
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

IssueSeverity = Literal["error", "warning", "ignore"]
ReportSeverity = Literal["error", "warning"]
SourceKind = Literal["yaml", "template"]
# Issue categories:
# - broken: the URL responded with a known dead-page status (404/410)
# - concatenated: the extracted token appears to contain multiple URLs jammed together
# - unreachable: the checker could not connect at all (timeout, DNS, TLS, etc.)
IssueCategory = Literal["broken", "concatenated", "unreachable"]


@dataclass(frozen=True)
class URLIssue:
    severity: ReportSeverity
    category: IssueCategory
    source_kind: SourceKind
    url: str
    sources: tuple[str, ...]
    status_code: int | None = None


@dataclass(frozen=True)
class URLCheckResult:
    checked_url_count: int
    ignored_url_count: int
    issues: tuple[URLIssue, ...]

    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)


@dataclass(frozen=True)
class URLSourceCollection:
    yaml_urls: dict[str, set[str]]
    document_urls: dict[str, set[str]]
    yaml_concatenated: dict[str, set[str]]
    document_concatenated: dict[str, set[str]]

    @property
    def unique_url_count(self) -> int:
        return len(set(self.yaml_urls) | set(self.document_urls))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate URLs in docassemble/*/data/questions and data/templates files"
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: current directory)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP timeout in seconds for each URL request (default: 10)",
    )
    parser.add_argument(
        "--skip-templates",
        action="store_true",
        help="Skip scanning data/templates (default: False, scan templates)",
    )
    parser.add_argument(
        "--ignore-urls",
        default="",
        help=(
            "Comma/newline-separated absolute URLs to ignore while checking "
            "(default: none)"
        ),
    )
    parser.add_argument(
        "--question-url-severity",
        "--yaml-url-severity",
        dest="yaml_url_severity",
        choices=("error", "warning", "ignore"),
        default="error",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--template-url-severity",
        dest="document_url_severity",
        choices=("error", "warning", "ignore"),
        default="warning",
        help="How to report broken or malformed URLs in template files (default: warning)",
    )
    parser.add_argument(
        "--document-url-severity",
        dest="document_url_severity",
        choices=("error", "warning", "ignore"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--unreachable-url-severity",
        choices=("error", "warning", "ignore"),
        default="warning",
        help="How to report URLs that could not be reached at all (default: warning)",
    )
    return parser.parse_args()


# File extensions likely to contain URLs worth checking.
_TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".yml",
        ".yaml",
        ".py",
        ".md",
        ".html",
        ".json",
        ".js",
        ".txt",
        ".j2",
    }
)

# Binary document formats to check
_DOCUMENT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
    }
)

# URL prefixes to whitelist (API families and endpoints requiring authentication).
_WHITELIST_URL_PREFIXES: frozenset[str] = frozenset(
    {
        "https://api.openai.com/v1/",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    }
)


def _iter_package_dirs(
    root: pathlib.Path, package_dirs: Iterable[pathlib.Path] | None = None
) -> Iterable[pathlib.Path]:
    if package_dirs is not None:
        seen: set[pathlib.Path] = set()
        for package_dir in package_dirs:
            resolved = package_dir.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.is_dir():
                yield resolved
        return

    questions_root = root / "docassemble"
    if not questions_root.exists():
        return

    for package_dir in sorted(questions_root.iterdir()):
        if not package_dir.is_dir():
            continue
        yield package_dir


def iter_question_files(
    root: pathlib.Path, package_dirs: Iterable[pathlib.Path] | None = None
) -> Iterable[pathlib.Path]:
    for package_dir in _iter_package_dirs(root, package_dirs):
        scan_dir = package_dir / "data" / "questions"
        if not scan_dir.exists():
            continue
        for file_path in scan_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in _TEXT_SUFFIXES:
                yield file_path


def iter_document_files(
    root: pathlib.Path, package_dirs: Iterable[pathlib.Path] | None = None
) -> Iterable[pathlib.Path]:
    allowed_suffixes = _TEXT_SUFFIXES | _DOCUMENT_SUFFIXES
    for package_dir in _iter_package_dirs(root, package_dirs):
        scan_dir = package_dir / "data" / "templates"
        if not scan_dir.exists():
            continue
        for file_path in scan_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in allowed_suffixes:
                yield file_path


def find_package_dir(file_path: pathlib.Path) -> pathlib.Path | None:
    resolved = file_path.resolve()
    search_start = resolved if resolved.is_dir() else resolved.parent
    for candidate in (search_start, *search_start.parents):
        if (candidate / "data" / "questions").exists():
            return candidate
    return None


def infer_package_dirs(question_files: Iterable[pathlib.Path]) -> list[pathlib.Path]:
    package_dirs = {
        package_dir
        for question_file in question_files
        if (package_dir := find_package_dir(question_file)) is not None
    }
    return sorted(package_dirs)


def infer_root(
    paths: Iterable[pathlib.Path], fallback: pathlib.Path | None = None
) -> pathlib.Path:
    resolved_paths = [path.resolve() for path in paths]
    for path in resolved_paths:
        search_start = path if path.is_dir() else path.parent
        for candidate in (search_start, *search_start.parents):
            if (candidate / "docassemble").is_dir():
                return candidate

    if resolved_paths:
        common_parent = pathlib.Path(
            os.path.commonpath(
                [str(path if path.is_dir() else path.parent) for path in resolved_paths]
            )
        )
        return common_parent

    if fallback is not None:
        return fallback.resolve()
    return pathlib.Path.cwd()


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=0,  # Don't retry on HTTP status codes; we only care about 404/410.
        backoff_factor=0.4,
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "ALActions-da_build-url-checker/1.0 "
                "(+https://github.com/SuffolkLITLab/ALActions)"
            )
        }
    )
    return session


def is_absolute_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_reserved_example_domain(url: str) -> bool:
    """Check if URL is in a reserved example domain (RFC 2606)."""
    example_domains: frozenset[str] = frozenset(
        {"example.com", "example.net", "example.org"}
    )
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in example_domains or any(
        hostname.endswith(f".{domain}") for domain in example_domains
    )


def is_whitelisted_url(url: str) -> bool:
    """Check if URL is in the whitelist (prefix-based for API families)."""
    return any(url.startswith(prefix) for prefix in _WHITELIST_URL_PREFIXES)


def extract_text_from_pdf(file_path: pathlib.Path) -> str:
    """Extract all text from a PDF file."""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as e:
        print(
            f"Warning: could not extract text from PDF {file_path}: {e}",
            file=sys.stderr,
        )
        return ""


def extract_text_from_docx(file_path: pathlib.Path) -> str:
    """Extract all text from a DOCX file."""
    try:
        result = docx2python(file_path)
        return result.text
    except Exception as e:
        print(
            f"Warning: could not extract text from DOCX {file_path}: {e}",
            file=sys.stderr,
        )
        return ""


def parse_url_token(raw_url: str) -> tuple[str | None, bool]:
    """Return (normalized_url, is_concatenated).

    *normalized_url* is ``None`` when the token should be skipped.
    *is_concatenated* is ``True`` when the token contains multiple URLs
    jammed together (a formatting error the caller should report).
    """
    url = raw_url.strip()
    if not url:
        return None, False

    # Only process explicit http/https URLs; skip fuzzy matches
    if not url.startswith(("http://", "https://")):
        return None, False

    # Link extraction in YAML/JS text can include trailing punctuation.
    url = url.rstrip(".,;:!?)>]}")

    # Query strings are valid. For concatenation checks, inspect only the
    # URL part before '?' so embedded URLs in query parameters don't trigger
    # false concatenation errors.
    url_without_query = url.split("?", 1)[0]
    num_schemes_in_base = len(re.findall(r"https?://", url_without_query))

    # Reject concatenated URLs like "...helphttps://..." (multiple schemes not at start)
    if num_schemes_in_base > 1:
        return None, True

    # Anything with literal quotes/angle brackets is likely a partial token.
    if any(ch in url for ch in ['"', "'", "<", ">"]):
        return None, False

    if not is_absolute_http_url(url):
        return None, False

    # If query parameters themselves include URLs (e.g. form_to_use=https://...),
    # normalize to the base URL so we don't flag nested URL parameter values.
    parsed = urlparse(url)
    if "http://" in parsed.query or "https://" in parsed.query:
        url = parsed._replace(query="", fragment="").geturl()

    return url, False


def parse_ignore_urls(raw: str) -> set[str]:
    """Parse comma/newline separated URLs to ignore."""
    if not raw:
        return set()

    tokens = re.split(r"[\n,]", raw)
    ignored_urls: set[str] = set()
    for token in tokens:
        candidate = token.strip()
        if not candidate:
            continue
        url, is_concatenated = parse_url_token(candidate)
        if is_concatenated:
            continue
        if url:
            ignored_urls.add(url)
    return ignored_urls


def extract_urls_from_file(
    file_path: pathlib.Path, linkify: LinkifyIt
) -> tuple[list[str], list[str]]:
    # Extract text based on file type
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text = extract_text_from_pdf(file_path)
    elif suffix == ".docx":
        text = extract_text_from_docx(file_path)
    else:
        # Plain text files
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Skip non-text files in questions directories.
            return [], []

    if not text:
        return [], []

    matches = linkify.match(text) or []
    found_urls: list[str] = []
    concatenated_urls: list[str] = []
    for match in matches:
        url, is_concatenated = parse_url_token(match.url)
        if is_concatenated:
            concatenated_urls.append(match.url.strip())
            continue
        if not url:
            continue
        if is_reserved_example_domain(url):
            continue
        found_urls.append(url)
    return found_urls, concatenated_urls


def _display_path(file_path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(file_path.relative_to(root))
    except ValueError:
        return str(file_path)


def collect_urls_from_files(
    file_paths: Iterable[pathlib.Path], root: pathlib.Path
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    linkify = LinkifyIt(options={"fuzzy_link": False})
    url_sources: dict[str, set[str]] = defaultdict(set)
    concatenated_sources: dict[str, set[str]] = defaultdict(set)
    for file_path in file_paths:
        rel_path = _display_path(file_path, root)
        urls, concatenated_urls = extract_urls_from_file(file_path, linkify)
        for url in urls:
            url_sources[url].add(rel_path)
        for bad_url in concatenated_urls:
            concatenated_sources[bad_url].add(rel_path)
    return url_sources, concatenated_sources


def collect_urls(
    root: pathlib.Path,
    question_files: Iterable[pathlib.Path] | None = None,
    package_dirs: Iterable[pathlib.Path] | None = None,
    check_documents: bool = True,
) -> URLSourceCollection:
    if question_files is None:
        question_files = iter_question_files(root, package_dirs=package_dirs)

    yaml_urls, yaml_concatenated = collect_urls_from_files(question_files, root)

    document_urls: dict[str, set[str]] = {}
    document_concatenated: dict[str, set[str]] = {}
    if check_documents:
        document_urls, document_concatenated = collect_urls_from_files(
            iter_document_files(root, package_dirs=package_dirs), root
        )

    return URLSourceCollection(
        yaml_urls=yaml_urls,
        document_urls=document_urls,
        yaml_concatenated=yaml_concatenated,
        document_concatenated=document_concatenated,
    )


_DEAD_STATUS_CODES: frozenset[int] = frozenset({404, 410})


def check_urls(
    session: requests.Session, urls: Iterable[str], timeout: int
) -> tuple[list[tuple[str, int]], list[str]]:
    """Return (broken, unreachable) for the given *urls*.

    *broken* contains ``(url, status_code)`` pairs for dead pages.
    *unreachable* lists URLs that could not be fetched at all.
    """
    broken: list[tuple[str, int]] = []
    unreachable: list[str] = []
    for url in sorted(urls):
        # Skip whitelisted URLs (e.g., API endpoints requiring authentication)
        if is_whitelisted_url(url):
            continue

        try:
            # stream=True avoids downloading large response bodies; the
            # context manager ensures the connection is released promptly.
            with session.get(
                url, allow_redirects=True, timeout=timeout, stream=True
            ) as response:
                if response.status_code in _DEAD_STATUS_CODES:
                    broken.append((url, response.status_code))
        except requests.RequestException as exc:
            print(f"Warning: could not check {url}: {exc}", file=sys.stderr)
            unreachable.append(url)
    return broken, unreachable


def _resolve_issue_severity(
    category: IssueCategory,
    source_kind: SourceKind,
    yaml_severity: IssueSeverity,
    document_severity: IssueSeverity,
    unreachable_severity: IssueSeverity,
) -> IssueSeverity:
    if category == "unreachable":
        return unreachable_severity
    if source_kind == "yaml":
        return yaml_severity
    return document_severity


def _append_issue(
    issues: list[URLIssue],
    *,
    category: IssueCategory,
    source_kind: SourceKind,
    url: str,
    sources: set[str],
    yaml_severity: IssueSeverity,
    document_severity: IssueSeverity,
    unreachable_severity: IssueSeverity,
    status_code: int | None = None,
) -> None:
    severity = _resolve_issue_severity(
        category=category,
        source_kind=source_kind,
        yaml_severity=yaml_severity,
        document_severity=document_severity,
        unreachable_severity=unreachable_severity,
    )
    if severity == "ignore":
        return
    issues.append(
        URLIssue(
            severity=severity,
            category=category,
            source_kind=source_kind,
            url=url,
            sources=tuple(sorted(sources)),
            status_code=status_code,
        )
    )


def run_url_check(
    *,
    root: pathlib.Path,
    question_files: Iterable[pathlib.Path] | None = None,
    package_dirs: Iterable[pathlib.Path] | None = None,
    timeout: int = 10,
    check_documents: bool = True,
    ignore_urls: Iterable[str] = (),
    yaml_severity: IssueSeverity = "error",
    document_severity: IssueSeverity = "warning",
    unreachable_severity: IssueSeverity = "warning",
) -> URLCheckResult:
    collected = collect_urls(
        root=root,
        question_files=question_files,
        package_dirs=package_dirs,
        check_documents=check_documents,
    )
    ignored_urls = set(ignore_urls)
    ignored_matches = sorted(
        ignored_urls & (set(collected.yaml_urls) | set(collected.document_urls))
    )
    for ignored in ignored_matches:
        collected.yaml_urls.pop(ignored, None)
        collected.document_urls.pop(ignored, None)

    issues: list[URLIssue] = []
    for bad_url, sources in sorted(collected.yaml_concatenated.items()):
        _append_issue(
            issues,
            category="concatenated",
            source_kind="yaml",
            url=bad_url,
            sources=sources,
            yaml_severity=yaml_severity,
            document_severity=document_severity,
            unreachable_severity=unreachable_severity,
        )
    for bad_url, sources in sorted(collected.document_concatenated.items()):
        _append_issue(
            issues,
            category="concatenated",
            source_kind="template",
            url=bad_url,
            sources=sources,
            yaml_severity=yaml_severity,
            document_severity=document_severity,
            unreachable_severity=unreachable_severity,
        )

    urls_to_check = set(collected.yaml_urls) | set(collected.document_urls)
    broken: list[tuple[str, int]] = []
    unreachable: list[str] = []
    if urls_to_check:
        session = build_session()
        broken, unreachable = check_urls(session, urls_to_check, timeout)

    for url, status_code in broken:
        if url in collected.yaml_urls:
            _append_issue(
                issues,
                category="broken",
                source_kind="yaml",
                url=url,
                sources=collected.yaml_urls[url],
                status_code=status_code,
                yaml_severity=yaml_severity,
                document_severity=document_severity,
                unreachable_severity=unreachable_severity,
            )
        if url in collected.document_urls:
            _append_issue(
                issues,
                category="broken",
                source_kind="template",
                url=url,
                sources=collected.document_urls[url],
                status_code=status_code,
                yaml_severity=yaml_severity,
                document_severity=document_severity,
                unreachable_severity=unreachable_severity,
            )

    for url in unreachable:
        if url in collected.yaml_urls:
            _append_issue(
                issues,
                category="unreachable",
                source_kind="yaml",
                url=url,
                sources=collected.yaml_urls[url],
                yaml_severity=yaml_severity,
                document_severity=document_severity,
                unreachable_severity=unreachable_severity,
            )
        if url in collected.document_urls:
            _append_issue(
                issues,
                category="unreachable",
                source_kind="template",
                url=url,
                sources=collected.document_urls[url],
                yaml_severity=yaml_severity,
                document_severity=document_severity,
                unreachable_severity=unreachable_severity,
            )

    severity_order = {"error": 0, "warning": 1}
    category_order = {"concatenated": 0, "broken": 1, "unreachable": 2}
    source_order = {"yaml": 0, "template": 1}
    ordered_issues = tuple(
        sorted(
            issues,
            key=lambda issue: (
                severity_order[issue.severity],
                category_order[issue.category],
                source_order[issue.source_kind],
                issue.url,
            ),
        )
    )
    return URLCheckResult(
        checked_url_count=len(urls_to_check),
        ignored_url_count=len(ignored_matches),
        issues=ordered_issues,
    )


def print_url_check_report(result: URLCheckResult) -> None:
    if result.ignored_url_count:
        print(f"Ignoring {result.ignored_url_count} URL(s) via --ignore-urls.")

    if result.checked_url_count == 0 and not result.issues:
        print("No absolute URLs found to check.")
        return

    if not result.issues:
        print(f"Checked {result.checked_url_count} URLs; none returned HTTP 404/410.")
        return

    source_labels = {
        "yaml": "question files",
        "template": "template files",
    }
    title_labels = {
        "concatenated": (
            "Found malformed URL text that appears to contain another URL in {source}:"
        ),
        "broken": "Found URLs returning HTTP 404/410 in {source}:",
        "unreachable": "Could not reach URLs in {source} to verify them:",
    }

    for severity in ("error", "warning"):
        matches = [issue for issue in result.issues if issue.severity == severity]
        if not matches:
            continue
        print(f"URL checker {severity}s:")
        for category in ("concatenated", "broken", "unreachable"):
            for source_kind in ("yaml", "template"):
                bucket = [
                    issue
                    for issue in matches
                    if issue.category == category and issue.source_kind == source_kind
                ]
                if not bucket:
                    continue
                print(title_labels[category].format(source=source_labels[source_kind]))
                for issue in bucket:
                    sources = ", ".join(issue.sources)
                    if issue.status_code is None:
                        print(f"- {issue.url} (found in: {sources})")
                    else:
                        print(
                            f"- [{issue.status_code}] {issue.url} "
                            f"(found in: {sources})"
                        )


def main() -> int:
    args = parse_args()
    root = pathlib.Path(args.root).resolve()
    result = run_url_check(
        root=root,
        timeout=args.timeout,
        check_documents=not args.skip_templates,
        ignore_urls=parse_ignore_urls(args.ignore_urls),
        yaml_severity=args.yaml_url_severity,
        document_severity=args.document_url_severity,
        unreachable_severity=args.unreachable_url_severity,
    )
    print_url_check_report(result)
    return 1 if result.has_errors() else 0


if __name__ == "__main__":
    raise SystemExit(main())
