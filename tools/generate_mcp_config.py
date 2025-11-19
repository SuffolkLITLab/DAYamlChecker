#!/usr/bin/env python3
"""
Generate a .vscode/mcp.json file for this project, searching for a local .venv by default
or taking a user-specified python/venv path.

This script is intended to be run from the project root. Usage examples:

# Use the local .venv (default detection)
python tools/generate_mcp_config.py

# Specify a venv path
python tools/generate_mcp_config.py --venv ~/.venv

# Specify a specific python executable
python tools/generate_mcp_config.py --python /usr/bin/python3

# Use the installed CLI instead of running module
python tools/generate_mcp_config.py --command dayamlchecker-mcp --args ''

# Use SSE transport
python tools/generate_mcp_config.py --transport sse

"""

import argparse
import json
import os
import sys
from pathlib import Path


def detect_default_python(workspace_root: Path):
    """Returns a tuple (command, args) to use for the MCP server by detecting a local .venv"""
    # If .venv exists in workspace root, use that python
    local_venv = workspace_root / ".venv"
    if local_venv.exists():
        # On Windows, users have Scripts; on POSIX, bin
        bin_py = local_venv / "bin" / "python"
        if not bin_py.exists():
            #!/usr/bin/env python3
            """Thin wrapper around the package entrypoint implementation."""
            from dayamlchecker.generate_mcp_config import main


            if __name__ == '__main__':
                raise SystemExit(main())
def write_mcp_config(path: Path, name: str, command: str, args: list, transport: str):
