import json
from pathlib import Path
import subprocess
import sys


def test_generate_mcp_config_creates_file(tmp_path):
    # Copy script path
    script = Path(__file__).parent.parent / "tools" / "generate_mcp_config.py"
    assert script.exists(), f"Script not found: {script}"

    # Run script specifying workspace as tmp_path
    cmd = [
        sys.executable,
        str(script),
        "--workspace",
        str(tmp_path),
        "--non-interactive",
    ]
    subprocess.check_call(cmd)

    cfg = tmp_path / ".vscode" / "mcp.json"
    assert cfg.exists(), "mcp.json was not generated"

    data = json.loads(cfg.read_text())
    assert "servers" in data
    assert "dayamlchecker" in data["servers"]
    server = data["servers"]["dayamlchecker"]
    assert "command" in server
    # args may be optional


def test_generate_mcp_config_uses_workspace_placeholder(tmp_path):
    # Setup a fake .venv in the workspace so the generation uses the ${workspaceFolder} placeholder
    script = Path(__file__).parent.parent / "tools" / "generate_mcp_config.py"
    venv_dir = tmp_path / ".venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_python = bin_dir / "python"
    fake_python.write_text("#!/usr/bin/env bash\necho test")
    fake_python.chmod(0o755)

    cmd = [
        sys.executable,
        str(script),
        "--workspace",
        str(tmp_path),
        "--non-interactive",
    ]
    subprocess.check_call(cmd)

    cfg = tmp_path / ".vscode" / "mcp.json"
    assert cfg.exists(), "mcp.json was not generated"
    data = json.loads(cfg.read_text())
    server = data["servers"]["dayamlchecker"]
    assert server["command"].startswith(
        "${workspaceFolder}"
    ), "Did not use ${workspaceFolder} placeholder"
