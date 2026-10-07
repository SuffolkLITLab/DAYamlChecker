"""Conservative spelling checks for visible interview text.

Checking is local. English, Russian and Swedish dictionaries come with spylls;
the Spanish dictionary is downloaded once on first use and cached.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
from html.parser import HTMLParser
import itertools
import importlib.resources
import inspect
import os
from pathlib import Path
import re
from typing import Iterable
import unicodedata

import requests
from spylls.hunspell import Dictionary  # type: ignore[import-untyped]

from dayamlchecker.accessibility import (
    FIELD_NON_LABEL_KEYS,
    _iter_fields,
    _extract_field_label,
    _extract_field_variable,
)
from dayamlchecker.messages import Finding, MessageId, Severity, make_finding
from dayamlchecker.style import (
    ParsedInterviewDocument,
    TextEntry,
    _user_facing_text_entries,
    _is_object_choice,
)

_WORDS = re.compile(r"(?<![\w])[^\W\d_]+(?:['’-][^\W\d_]+)*(?![\w])")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^\n]*?\)")
_TECHNICAL = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"
    r"|\b[\w-]+\.(?:pdf|docx?|ya?ml|png|jpe?g|html|org|com|gov|edu)\b",
    re.IGNORECASE,
)
_GEOGRAPHIC_FIELD = re.compile(
    r"\b(?:courts?|count(?:y|ies)|parish|borough|cit(?:y|ies)|town|municipality|"
    r"state|province|territory|country|district|division)\b",
    re.IGNORECASE,
)
_PERSON_NAME = re.compile(
    r"\b[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*(?:[ \t]+[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*)+\b"
)
_CHOICE_LOCATIONS = frozenset({"choices", "dropdown", "buttons"})
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+(.+)$")
_CREDIT_HEADING = re.compile(
    r"\b(?:authors?|contributors?|credits|copyright)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class SpellcheckOptions:
    allowed_words: frozenset[str] = frozenset()
    languages: tuple[str, ...] = ("en",)
    dictionaries: tuple[tuple[str, str], ...] = ()
    severity: Severity = Severity.WARNING

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", Severity(self.severity))
        object.__setattr__(
            self,
            "allowed_words",
            frozenset(filter(None, map(normalize_word, self.allowed_words))),
        )
        if isinstance(self.languages, str) or not self.languages:
            raise ValueError(
                "spellcheck languages must be a nonempty sequence of codes"
            )
        languages = tuple(dict.fromkeys(normalize_language(v) for v in self.languages))
        dictionaries = tuple(
            (normalize_language(code), str(Path(path).expanduser().resolve()))
            for code, path in self.dictionaries
        )
        if len({code for code, _ in dictionaries}) != len(dictionaries):
            raise ValueError("duplicate spellcheck dictionary language")
        for code, path in dictionaries:
            for suffix in (".aff", ".dic"):
                if not Path(path + suffix).is_file():
                    raise ValueError(
                        f"cannot read spellcheck dictionary {code}: {path + suffix}"
                    )
            try:
                _dictionary(path)
            except (OSError, UnicodeError, ValueError, re.error) as exc:
                raise ValueError(
                    f"cannot load spellcheck dictionary {code}: {exc}"
                ) from exc
        for language in languages:
            if language in dict(dictionaries):
                continue
            if language in _REMOTE_DICTIONARIES:
                # Download now so a failure is a configuration error, not a
                # crash partway through checking.
                _remote_dictionary_prefix(language)
            elif language not in _SPYLLS_DICTIONARIES:
                raise ValueError(
                    f"unsupported spellcheck language {language!r}; "
                    f"built in: {', '.join(_BUILTIN_LANGUAGES)}; "
                    "supply a custom Hunspell dictionary for other languages or regions"
                )
        object.__setattr__(self, "languages", languages)
        object.__setattr__(self, "dictionaries", dictionaries)

    @property
    def dictionary_sources(self) -> tuple[str, ...]:
        overrides = dict(self.dictionaries)
        return tuple(overrides.get(language, language) for language in self.languages)


@dataclass(frozen=True)
class SpellingTextEntry(TextEntry):
    geographic_choices: bool = False


def normalize_word(word: str) -> str:
    """Normalize a word as spelling_text() normalizes interview prose."""
    return unicodedata.normalize("NFC", word.strip().replace("’", "'")).lower()


def _base_language(language: str) -> str:
    return language.strip().lower().replace("_", "-").split("-", 1)[0]


def normalize_language(language: str) -> str:
    """Normalize tags while preserving dialects that require custom dictionaries."""
    code = language.strip().lower().replace("_", "-")
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", code):
        raise ValueError(f"invalid spellcheck language code {language!r}")
    return {"en-us": "en", "es-us": "es", "sv-se": "sv", "ru-ru": "ru"}.get(code, code)


@dataclass(frozen=True)
class _RemoteDictionary:
    name: str
    base_url: str
    sha256: dict[str, str]  # by file suffix


# Dictionaries shipped with spylls.
_SPYLLS_DICTIONARIES = {"en": "en_US", "ru": "ru", "sv": "sv_SE"}
# Dictionaries downloaded on first use rather than redistributed. The pinned
# upstream commit and hashes keep every run on identical files.
_REMOTE_DICTIONARIES = {
    "es": _RemoteDictionary(
        # RLA-ES Spanish (US), as distributed by LibreOffice.
        name="es_US",
        base_url="https://raw.githubusercontent.com/LibreOffice/dictionaries/"
        "762abe74008b94b2ff06db6f4024b59a8254c467/es/",
        sha256={
            ".aff": "674c5a4b4d39fd3b4452f045a4e6e0649db4a2ce23f5903df8c311e21f1a757c",
            ".dic": "d46932a5c0ec3881fdf265333df4de45a73de51741baedcb5bb54d37b03979c8",
        },
    ),
}
_BUILTIN_LANGUAGES = sorted(_SPYLLS_DICTIONARIES.keys() | _REMOTE_DICTIONARIES)
_SPYLLS_DATA = Path(inspect.getfile(Dictionary)).parent / "data"


def dictionary_cache_dir() -> Path:
    """Where downloaded dictionaries are kept: $DAYAMLCHECKER_CACHE_DIR, else
    the platform's user cache directory."""
    if configured := os.environ.get("DAYAMLCHECKER_CACHE_DIR"):
        return Path(configured).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "dayamlchecker" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / (
        "dayamlchecker"
    )


def _remote_dictionary_prefix(language: str) -> str:
    """Return the cached dictionary prefix, downloading missing or bad files."""
    remote = _REMOTE_DICTIONARIES[language]
    # Key the directory on the content, so a pin update never reuses old files.
    directory = (
        dictionary_cache_dir() / "dictionaries" / language / remote.sha256[".dic"][:16]
    )
    offline_hint = (
        f"to work offline, supply --spellcheck-dictionary {language}=PATH "
        "with a local Hunspell dictionary"
    )
    for suffix, expected in remote.sha256.items():
        path = directory / (remote.name + suffix)
        try:
            if path.is_file() and _sha256(path.read_bytes()) == expected:
                continue
        except OSError:
            pass
        url = remote.base_url + remote.name + suffix
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(
                f"cannot download the {language} spellcheck dictionary from {url}: "
                f"{exc}; {offline_hint}"
            ) from exc
        if _sha256(response.content) != expected:
            raise ValueError(
                f"the downloaded {language} spellcheck dictionary {url} does not "
                f"match its expected SHA-256; {offline_hint}"
            )
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # Write then rename, so concurrent runs never read a partial file.
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_bytes(response.content)
            os.replace(temporary, path)
        except OSError as exc:
            raise ValueError(
                f"cannot cache the {language} spellcheck dictionary in "
                f"{directory}: {exc}; set DAYAMLCHECKER_CACHE_DIR to a writable "
                "directory"
            ) from exc
    return str(directory / remote.name)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=16)
def _dictionary(source: str) -> Dictionary:
    if source in _REMOTE_DICTIONARIES:
        return Dictionary.from_files(_remote_dictionary_prefix(source))
    if source in _SPYLLS_DICTIONARIES:
        # Resolve spylls' bundled copy explicitly: from_files("en_US") prefers
        # an en_US.aff/.dic in the current directory when one exists.
        name = _SPYLLS_DICTIONARIES[source]
        return Dictionary.from_files(
            str(_SPYLLS_DATA / Dictionary.DISTRIBUTED[name] / name)
        )
    return Dictionary.from_files(source)


@lru_cache(maxsize=32768)
def dictionary_accepts(word: str, sources: tuple[str, ...] = ("en",)) -> bool:
    return any(bool(_dictionary(source).lookup(word)) for source in sources)


def read_wordlist(text: str) -> frozenset[str]:
    """Parse one normalized word per line, ignoring blank and # comment lines."""
    return frozenset(
        normalize_word(line)
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def options_from_cli(
    *,
    languages: Iterable[str],
    dictionary_specs: Iterable[str],
    wordlists: Iterable[Path],
    ignore_words: Iterable[str] = (),
    severity: Severity | str = Severity.WARNING,
) -> SpellcheckOptions:
    """Build options from LANG=PATH dictionaries and wordlist files.

    Raise ValueError with a user-facing message for invalid input.
    """
    allowed = set(ignore_words)
    for wordlist in wordlists:
        try:
            allowed |= read_wordlist(wordlist.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise ValueError(
                f"cannot read spellcheck wordlist {wordlist}: {exc}"
            ) from exc
    dictionaries: list[tuple[str, str]] = []
    for specification in dictionary_specs:
        code, separator, path = specification.partition("=")
        if not separator or not path:
            raise ValueError(
                "spellcheck dictionary requires LANG=PATH (without .aff/.dic)"
            )
        dictionaries.append((code, path))
    return SpellcheckOptions(
        allowed_words=frozenset(allowed),
        languages=tuple(languages)
        or tuple(code for code, _ in dictionaries)
        or ("en",),
        dictionaries=tuple(dictionaries),
        severity=Severity(severity),
    )


@lru_cache(maxsize=1)
def _domain_words() -> frozenset[str]:
    return read_wordlist(
        importlib.resources.files("dayamlchecker")
        .joinpath("data/spelling_words.txt")
        .read_text(encoding="utf-8")
    )


class _VisibleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "code", "pre"}:
            self.hidden.append(tag)
        self.parts.append(" ")
        if tag == "img" and not self.hidden:
            self.parts.extend(value for name, value in attrs if name == "alt" and value)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.hidden:
            self.hidden = self.hidden[: self.hidden.index(tag)]
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def _without_expressions(text: str) -> str:
    """Remove balanced Mako expressions, including nested dicts and quotes."""
    parts: list[str] = []
    pos = 0
    while (start := text.find("${", pos)) != -1:
        parts.append(text[pos:start])
        end, depth, quote = start + 2, 1, ""
        while end < len(text) and depth:
            char = text[end]
            if quote:
                if char == "\\":
                    end += 2
                    continue
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            end += 1
        parts.append(" ")
        pos = end
    parts.append(text[pos:])
    return "".join(parts)


def spelling_text(text: str) -> str:
    """Keep prose while discarding template, Markdown, HTML and URL syntax."""
    text = re.sub(r"<%[\s\S]*?%>", " ", text)
    text = _without_expressions(text)
    text = re.sub(r"(?m)^[ \t]*%.*$", " ", text)
    text = re.sub(r"(?ms)^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[^\n]*", " ", text)
    text = re.sub(r"`+[^`]*`+", " ", text)
    text = _LINK.sub(r"\1", text)
    text = re.sub(r":[A-Za-z][\w-]*:", " ", text)  # Docassemble icons
    text = re.sub(r"\b([^\W\d_]+)\([a-z]{1,4}\)", r"\1", text)  # child(ren)
    text = re.sub(r"\[(?:FILE|EMOJI|[A-Z][A-Z_ ]*)\b[^\]]*\]", " ", text)
    text = _TECHNICAL.sub(" ", text)
    parser = _VisibleHTML()
    parser.feed(text)
    parser.close()
    return unicodedata.normalize("NFC", "".join(parser.parts).replace("’", "'"))


def _geographic_choice_field(field: dict) -> bool:
    # Use the interview's schema to identify names, rather than maintaining a
    # county/court/city dictionary specific to one jurisdiction. Only choice
    # labels are affected: questions, instructions and help remain checked.
    context = (
        " ".join(
            (
                _extract_field_label(field),
                _extract_field_variable(field),
                str(field.get("question", "")),
                str(field.get("help", "")),
            )
        )
        .replace("_", " ")
        .replace(".", " ")
    )
    if _GEOGRAPHIC_FIELD.search(context):
        return True
    return bool(
        re.search(r"\bhearing\b", context, re.IGNORECASE)
        and re.search(r"\blocation\b", context, re.IGNORECASE)
    )


def _lowercase_keys(
    docs: Iterable[ParsedInterviewDocument],
) -> list[ParsedInterviewDocument]:
    return [
        replace(doc, doc={str(key).lower(): value for key, value in doc.doc.items()})
        for doc in docs
    ]


def _declared_author_names(docs: list[ParsedInterviewDocument]) -> frozenset[str]:
    names: set[str] = set()
    for parsed in docs:
        metadata = parsed.doc.get("metadata")
        if not isinstance(metadata, dict):
            continue
        authors = metadata.get("authors", [])
        if not isinstance(authors, list):
            continue
        for author in authors:
            name = author.get("name", "") if isinstance(author, dict) else author
            if isinstance(name, str):
                names.update(m.group().lower() for m in _WORDS.finditer(name))
    return frozenset(names)


def _without_credit_names(text: str) -> str:
    """Exclude personal-name spans in explicitly marked attribution sections.

    Retain prose in those sections; a misspelling in a contributor description
    is still useful to flag. Heading scope ends at the next peer/parent heading.
    """
    credit_level: int | None = None
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        heading = _HEADING.match(line)
        if heading:
            level = len(line.lstrip().split()[0])
            if credit_level is not None and level <= credit_level:
                credit_level = None
            if _CREDIT_HEADING.search(heading[1]):
                credit_level = level
        if credit_level is not None or re.search(
            r"(?:©|&copy;|\bcopyright\b)", line, re.IGNORECASE
        ):
            line = _PERSON_NAME.sub(lambda m: " " * len(m.group()), line)
        lines.append(line)
    return "".join(lines)


def spelling_entries(
    docs: Iterable[ParsedInterviewDocument],
    options: SpellcheckOptions | None = None,
) -> list[SpellingTextEntry]:
    """Select visible text in enabled languages, excluding code/stored values."""
    options = options or SpellcheckOptions()
    docs = _lowercase_keys(docs)
    default_language = next(
        (str(p.doc["default language"]) for p in docs if p.doc.get("default language")),
        "",
    )
    enabled_bases = {_base_language(language) for language in options.languages}
    entries: list[SpellingTextEntry] = []
    for parsed in docs:
        declared = parsed.doc.get("language") or default_language
        if declared:
            # A declared translation outside the enabled dictionaries must not
            # be checked against an unrelated language. Configured dictionaries
            # remain a union within eligible blocks, including bilingual prose.
            if _base_language(str(declared)) not in enabled_bases:
                continue
        fields = list(_iter_fields(parsed.doc))
        for entry in _user_facing_text_entries([parsed]):
            if (
                entry.location.endswith(".first_key")
                and entry.text in FIELD_NON_LABEL_KEYS
            ):
                continue
            field_choice = re.fullmatch(r"fields\[(\d+)\]\.choices", entry.location)
            choice_owner = (
                fields[int(field_choice[1])]
                if field_choice
                else parsed.doc if entry.location in _CHOICE_LOCATIONS else None
            )
            if choice_owner is not None and _is_object_choice(choice_owner):
                continue
            geographic = choice_owner is not None and _geographic_choice_field(
                choice_owner
            )
            entries.append(
                SpellingTextEntry(
                    entry.location,
                    entry.text,
                    entry.line_number,
                    entry.screen_id,
                    geographic,
                )
            )
        if (
            "template" in parsed.doc
            and isinstance(parsed.doc.get("content"), str)
            and parsed.doc.get("content type") in {None, "text/html", "text/plain"}
        ):
            entries.append(
                SpellingTextEntry(
                    "content",
                    parsed.doc["content"],
                    parsed.line_for_key("content"),
                    parsed.screen_id,
                )
            )
    return entries


def _accepted(
    word: str, allowed: frozenset[str], sources: tuple[str, ...], english: bool
) -> bool:
    lower = word.lower()
    if (
        lower in allowed
        or dictionary_accepts(word, sources)
        or dictionary_accepts(lower, sources)
        or dictionary_accepts(lower.capitalize(), sources)
    ):
        return True
    if (
        english
        and lower.endswith("'s")
        and _accepted(word[:-2], allowed, sources, english)
    ):
        return True
    if "-" in word and all(
        _accepted(part, allowed, sources, english) for part in word.split("-")
    ):
        return True
    if english and "-" in word:
        prefix, rest = word.split("-", 1)
        if prefix.lower() in {"pre", "non", "un", "re", "co", "sur"} and _accepted(
            rest, allowed, sources, english
        ):
            return True
    return False


def _checkable(word: str) -> bool:
    """Words eligible for reporting: not short, acronyms or mixed case."""
    return (
        len(word) >= 3 and not word.isupper() and not any(c.isupper() for c in word[1:])
    )


@lru_cache(maxsize=4096)
def _close_dictionary_word(word: str, sources: tuple[str, ...]) -> bool:
    """Rescue title-case typos without warning on every unfamiliar name.

    Require a nearby lowercase dictionary word: proper names alone are not
    evidence of an error. Restrict this extra work to longer capitalized words.
    """
    if len(word) < 6 or len(word) > 40:
        return False
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    letters = set("abcdefghijklmnopqrstuvwxyz")
    for source in sources:
        if source != "en":
            letters.update((_dictionary(source).aff.TRY or "").lower())
    # Substitutions are especially prone to confusing names with ordinary
    # words (e.g. Quinten / quintet), so omit them for this title-case rescue.
    # Generate lazily, cheapest edits first, and stop at the first hit. Look
    # candidates up directly so they do not evict entries from the word cache.
    # The few duplicate candidates (repeated letters) cost less than deduping.
    edits = itertools.chain(
        (left + right[1:] for left, right in splits if right),
        (
            left + right[1] + right[0] + right[2:]
            for left, right in splits
            if len(right) > 1
        ),
        (left + char + right for left, right in splits for char in letters),
    )
    dictionaries = [_dictionary(source) for source in sources]
    return any(
        dictionary.lookup(candidate)
        for candidate in edits
        for dictionary in dictionaries
    )


def find_spelling_findings(
    *,
    docs: Iterable[ParsedInterviewDocument],
    input_file: str | None,
    options: SpellcheckOptions | None = None,
) -> list[Finding]:
    """Report unknown prose words once per entry; never rewrite interview text.

    Prioritize precision: skip names/acronyms/mixed case, short tokens and text
    that appears to be another language. Apart from explicit legal spelling
    recommendations, this does not detect real-word typos.
    """
    options = options or SpellcheckOptions()
    docs = _lowercase_keys(docs)
    author_names = _declared_author_names(docs)
    sources = options.dictionary_sources
    bases = {_base_language(language) for language in options.languages}
    english = "en" in bases
    allowed = options.allowed_words | (_domain_words() if english else frozenset())
    findings: list[Finding] = []
    for entry in spelling_entries(docs, options):
        text = spelling_text(_without_credit_names(entry.text))
        words = list(_WORDS.finditer(text))
        # Accept each reportable word once; acronyms, short and mixed-case words
        # are never reported, nor counted in the other-language ratio, so
        # acronym-heavy English prose is still checked.
        accepted = {
            m.group(): _accepted(m.group(), allowed, sources, english)
            for m in words
            if _checkable(m.group())
        }
        checked = [accepted[m.group()] for m in words if m.group() in accepted]
        if len(checked) >= 8 and sum(checked) / len(checked) < 0.6:
            continue
        seen: set[str] = set()
        for match in words:
            word, lower = match.group(), match.group().lower()
            if lower in seen or lower in allowed:
                continue
            suggestion = _legal_spelling_suggestion(word, options.languages, allowed)
            if not suggestion and (
                accepted.get(word, True) or (bases == {"en"} and not word.isascii())
            ):
                continue
            if (
                not suggestion
                and word[0].isupper()
                and (
                    entry.geographic_choices
                    or lower in author_names
                    or not _close_dictionary_word(lower, sources)
                )
            ):
                continue
            seen.add(lower)
            finding = make_finding(
                (
                    MessageId.SPELLING_COMMON_LEGAL_TYPO
                    if suggestion
                    else MessageId.SPELLING_POSSIBLE_TYPO
                ),
                file_name=input_file,
                line_number=entry.line_number,
                word=word,
                suggestion=suggestion,
                location=entry.location,
                screen_id=entry.screen_id,
                snippet=re.sub(
                    r"\s+",
                    " ",
                    text[max(0, match.start() - 80) : match.end() + 120],
                ).strip(),
            )
            findings.append(replace(finding, severity_override=options.severity))
    return findings


def _legal_spelling_suggestion(
    word: str, languages: tuple[str, ...], allowed: frozenset[str]
) -> str | None:
    """Explicit legal corrections bypass dictionary variants and acronym filters."""
    if "-" in word:
        parts = word.split("-")
        replacements = [
            _legal_spelling_suggestion(part, languages, allowed) or part
            for part in parts
        ]
        compound = "-".join(replacements)
        return compound if compound != word else None
    lower = word.lower()
    stem = lower.removesuffix("'s")
    suffix = word[len(stem) :]
    if lower in allowed or stem in allowed:
        return None
    if stem == "hippa" and any(_base_language(v) == "en" for v in languages):
        return "HIPAA" + suffix
    # The preference for judgment is US English; a custom British English
    # dictionary should retain its own accepted spelling variants.
    if "en" not in languages:
        return None
    corrected = {"judgement": "judgment", "judgements": "judgments"}.get(stem)
    if not corrected:
        return None
    if word.isupper():
        corrected = corrected.upper()
    elif word[0].isupper():
        corrected = corrected.capitalize()
    return corrected + suffix
