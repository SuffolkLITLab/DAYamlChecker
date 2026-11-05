"""Reproducible style/accessibility sample; findings are candidates, not precision labels."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from dayamlchecker.accessibility import find_accessibility_findings
from dayamlchecker.style import StyleLintOptions, find_style_findings
from dayamlchecker.yaml_structure import parse_interview_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, help="Directory containing checked-out repositories"
    )
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--review-level", choices=["precision", "thorough"], default="precision"
    )
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--model", help="OpenAI-compatible model/deployment ID")
    args = parser.parse_args()
    if args.stride < 1:
        parser.error("--stride must be positive")
    repos = sorted(p for p in args.root.iterdir() if p.is_dir())[:: args.stride]
    rows, files = [], []
    options = StyleLintOptions(
        enabled=True,
        include_llm=args.llm,
        review_level=args.review_level,
        openai_model=args.model,
    )
    for repo in repos:
        for path in sorted(repo.glob("docassemble/*/data/questions/*.y*ml")):
            source = path.read_text()
            docs, errors = parse_interview_documents(source, str(path))
            findings = list(errors) + find_style_findings(
                docs=docs, input_file=str(path), options=options
            )
            # The hidden-suggestion notice is a summary, not a candidate finding.
            findings = [f for f in findings if f.code != "IS749"]
            for doc in docs:
                findings += find_accessibility_findings(
                    doc=doc.doc,
                    source_code=doc.source_code,
                    document_start_line=doc.document_start_line,
                    input_file=str(path),
                )
            files.append(
                {
                    "path": str(path),
                    "sha256": hashlib.sha256(source.encode()).hexdigest(),
                }
            )
            rows.extend(
                {
                    "file": str(path),
                    "line": f.line_number,
                    "id": str(f.message_id),
                    "context": dict(f.context),
                    "message": f.message,
                }
                for f in findings
            )
    result = {
        "repos": [p.name for p in repos],
        "files": files,
        "review_level": args.review_level,
        "llm": args.llm,
        "model": options.resolved_openai_model() if args.llm else None,
        "counts": dict(Counter(r["id"] for r in rows)),
        "findings": rows,
    }
    args.output.write_text(json.dumps(result, indent=2, default=str))
    print(
        json.dumps(
            {
                "repos": len(repos),
                "files": len(files),
                "findings": len(rows),
                "counts": result["counts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
