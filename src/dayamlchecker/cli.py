from __future__ import annotations

import sys
from typing import TextIO

from dayamlchecker.code_formatter import main as format_main
from dayamlchecker.yaml_structure import main as check_main


def _print_help(output_stream: TextIO) -> None:
    print(
        "usage: dayaml <command> [<args>]\n\n"
        "Commands:\n"
        "  check   Validate Docassemble YAML files (defaults to ./docassemble)\n"
        "  format  Format Python code blocks in Docassemble YAML files (defaults to ./docassemble)\n\n"
        "Use 'dayaml <command> --help' for command-specific options.\n"
        "The 'check' command supports '--show-experimental'/\"--no-show-experimental\" to control inclusion of the legacy REAL ERROR prefix.",
        file=output_stream,
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if not args:
        _print_help(sys.stderr)
        return 2

    if args[0] in {"-h", "--help"}:
        _print_help(sys.stdout)
        return 0

    command, *command_args = args
    if command == "check":
        if not command_args:
            command_args = ["./docassemble"]
        return check_main(command_args)
    if command == "format":
        if not command_args:
            command_args = ["./docassemble"]
        return format_main(command_args)

    print(f"Unknown command: {command}", file=sys.stderr)
    _print_help(sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
