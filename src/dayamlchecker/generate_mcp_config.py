"""
Entry point for generating a vscode `mcp.json` for the workspace. This is the package version of
`tools/generate_mcp_config.py` and exposes a `main()` function that can be installed as a console script.
"""

from pathlib import Path
import json
import os
import sys


def detect_default_python(workspace_root: Path):
    local_venv = workspace_root / ".venv"
    if local_venv.exists():
        bin_py = local_venv / "bin" / "python"
        if not bin_py.exists():
            bin_py = local_venv / "Scripts" / "python.exe"
        if bin_py.exists():
            return str(bin_py), ["-m", "dayamlchecker.mcp.server"]
    return sys.executable, ["-m", "dayamlchecker.mcp.server"]


def write_mcp_config(path: Path, name: str, command: str, args: list, transport: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {"servers": {name: {"type": transport, "command": command}}}
    if args:
        config["servers"][name]["args"] = args
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, sort_keys=False)
    print(f"Wrote {path}")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Generate .vscode/mcp.json for DAYamlChecker")
    parser.add_argument("--workspace", default=os.getcwd(), help="Workspace root (default: current directory)")
    parser.add_argument("--venv", help="Path to venv root (e.g., ~/venv or /home/user/venv)")
    parser.add_argument("--python", help="Path to python executable to use (overrides venv) - e.g. /usr/bin/python3")
    parser.add_argument("--command", help="Command to run for the MCP server (e.g. dayamlchecker-mcp). If not provided, by default we'll use python -m dayamlchecker.mcp.server", default=None)
    parser.add_argument("--args", help="JSON array of args to pass to the command (for example: '[-m, dayamlchecker.mcp.server]')")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio", help="Transport type for MCP server (stdio is default)")
    parser.add_argument("--name", default="dayamlchecker", help="Server name in mcp.json")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt; write with defaults or provided flags")

    args = parser.parse_args(argv)
    workspace_root = Path(args.workspace).resolve()
    if not workspace_root.exists():
        print(f"Workspace root not found: {workspace_root}")
        return 2

    command = None
    command_args = None
    if args.command:
        command = args.command
        if args.args:
            command_args = json.loads(args.args)
        else:
            command_args = []
    else:
        if args.python:
            command = args.python
            command_args = ["-m", "dayamlchecker.mcp.server"]
        elif args.venv:
            venv_path = Path(os.path.expanduser(args.venv))
            py = venv_path / "bin" / "python"
            if not py.exists():
                py = venv_path / "Scripts" / "python.exe"
            if py.exists():
                command = str(py)
                command_args = ["-m", "dayamlchecker.mcp.server"]
            else:
                print(f"No python found in venv path: {venv_path}")
                return 2
        else:
            detected_cmd, detected_args = detect_default_python(workspace_root)
            command = detected_cmd
            command_args = detected_args

    # If python inside workspace's .venv, use ${workspaceFolder} placeholder
    if command and isinstance(command, str) and command.startswith(str(workspace_root / ".venv")):
        rel = Path(command).relative_to(workspace_root)
        placeholder = "${workspaceFolder}/" + str(rel).replace('\\\\', '/')
        command_to_write = placeholder
    else:
        command_to_write = command

    mcp_config_file = workspace_root / ".vscode" / "mcp.json"
    write_mcp_config(mcp_config_file, args.name, command_to_write, command_args, args.transport)

    print("\nNext steps:")
    print(" - Open the project in VS Code. The MCP server should start automatically when you use tools or Copilot Chat.")
    if args.transport == "sse":
        print(" - Note: If you picked 'sse', you may want to run the server via 'mcp run -t sse [command]' when debugging or deploying.")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
