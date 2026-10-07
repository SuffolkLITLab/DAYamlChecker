"""Compare naive dictionary warnings and conservative spelling on a YAML corpus.

Run with: python scripts/evaluate_spelling.py ~/all_interviews --output /tmp/spelling.json
The JSON is an audit queue, not automatically labelled ground truth.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayamlchecker._jinja import uses_jinja
from dayamlchecker.spelling import (
    dictionary_accepts,
    find_spelling_findings,
    options_from_cli,
    spelling_entries,
)
from dayamlchecker.yaml_structure import (
    _collect_yaml_files,
    parse_interview_documents,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wordlist", type=Path, action="append", default=[])
    parser.add_argument("--language", action="append", default=[])
    parser.add_argument(
        "--dictionary", action="append", default=[], metavar="LANG=PATH"
    )
    args = parser.parse_args()
    try:
        options = options_from_cli(
            languages=args.language,
            dictionary_specs=args.dictionary,
            wordlists=args.wordlist,
        )
    except ValueError as exc:
        parser.error(str(exc))
    start = time.monotonic()
    files = sorted(set(path.resolve() for path in _collect_yaml_files([args.root])))
    records: dict[str, list[dict]] = {"baseline": [], "filtered": []}
    failures: list[dict] = []
    parsed_files = blocks = entries_count = tokens = 0
    for path in files:
        try:
            content = (
                path.read_text(encoding="utf-8")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )
            if uses_jinja(content):
                # Match the production checker's preprocessing, without running
                # unrelated lints or making network requests.
                from dayamlchecker._jinja import render_yaml

                content, missing, unknown = render_yaml(content, str(path))
                if missing or unknown:
                    failures.append(
                        {"file": str(path), "error": "partial Jinja rendering"}
                    )
            docs, parse_errors = parse_interview_documents(content, str(path))
            if parse_errors:
                raise ValueError(parse_errors[0].context.get("error", "YAML error"))
        except Exception as exc:
            failures.append({"file": str(path), "error": str(exc)})
            continue
        parsed_files += 1
        blocks += len(docs)
        entries = spelling_entries(docs, options)
        entries_count += len(entries)
        for entry in entries:
            words = re.findall(r"\b[^\W\d_]+(?:['’][^\W\d_]+)*\b", entry.text)
            tokens += len(words)
            seen = set()
            for word in words:
                lower = word.lower().replace("’", "'")
                if (
                    lower in seen
                    or dictionary_accepts(word, options.dictionary_sources)
                    or dictionary_accepts(lower, options.dictionary_sources)
                ):
                    continue
                seen.add(lower)
                records["baseline"].append(
                    {
                        "file": str(path.relative_to(args.root.resolve())),
                        "line": entry.line_number,
                        "location": entry.location,
                        "word": word,
                        "snippet": re.sub(r"\s+", " ", entry.text).strip()[:300],
                    }
                )
        records["filtered"].extend(
            {
                "file": str(path.relative_to(args.root.resolve())),
                "line": finding.line_number,
                **finding.context,
            }
            for finding in find_spelling_findings(
                docs=docs, input_file=str(path), options=options
            )
        )
    summary: dict[str, Any] = {
        "files_discovered": len(files),
        "files_parsed": parsed_files,
        "blocks": blocks,
        "text_entries": entries_count,
        "raw_word_tokens": tokens,
        "parse_or_render_issues": len(failures),
        "elapsed_seconds": round(time.monotonic() - start, 2),
    }
    for name, findings in records.items():
        counts = Counter(record["word"].lower() for record in findings)
        summary[name] = {
            "warnings": len(findings),
            "unique_words": len(counts),
            "files_with_warnings": len({f["file"] for f in findings}),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"summary": summary, "issues": failures, **records},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
