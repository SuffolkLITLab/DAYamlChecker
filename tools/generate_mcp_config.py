#!/usr/bin/env python3
"""Thin wrapper around the packaged `dayamlchecker.generate_mcp_config` CLI.

This script delegates to the package version (`python -m dayamlchecker.generate_mcp_config`) so
contributors can run it from the repo using `python tools/generate_mcp_config.py` while the
packaged console script `dayamlchecker-gen-mcp` (installed via `pip`) is available for users.
"""

from dayamlchecker.generate_mcp_config import main


if __name__ == '__main__':
    raise SystemExit(main())
