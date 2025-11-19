#!/usr/bin/env python3
"""Thin wrapper around the packaged `dayamlchecker.generate_mcp_config` CLI.

This script delegates to the package version (`python -m dayamlchecker.generate_mcp_config`) so
contributors can run it from the repo using `python tools/generate_mcp_config.py` while the
packaged console script `dayamlchecker-gen-mcp` (installed via `pip`) is available for users.
"""

"""Run the packaged `generate_mcp_config` if available, otherwise run the local
script so developers can use this wrapper without installing the package.
"""
import runpy
import pathlib

try:
    # Prefer the installed package entrypoint when available
    from dayamlchecker.generate_mcp_config import main as packaged_main
except Exception:
    packaged_main = None


def main():
    if packaged_main:
        return packaged_main()
    # Fall back to running the local copy in the repo for development
    script_path = pathlib.Path(__file__).resolve().parent.parent / "dayamlchecker" / "generate_mcp_config.py"
    if script_path.exists():
        runpy.run_path(str(script_path), run_name="__main__")
        return 0
    else:
        print("dayamlchecker.generate_mcp_config not installed and local script not found.")
        print("Install the package into your venv with: pip install -e '.[mcp]' or pip install 'dayamlchecker[mcp]'.")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
