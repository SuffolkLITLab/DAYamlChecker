# DAYamlChecker MCP Server

This document describes how to install, configure, and run the DAYamlChecker Model Context Protocol (MCP) server. This server allows AI assistants like GitHub Copilot to validate Docassemble YAML code directly within your editor.

## Installation

To use the MCP server, you need to install the package with the `mcp` extra:

```bash
# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with MCP support
pip install "dayamlchecker[mcp]"
```

## VS Code & GitHub Copilot Integration

The primary way to use this server is with Visual Studio Code and GitHub Copilot.

### Automatic Setup (Recommended)

### Generate a VS Code MCP configuration

Recommended: after installing DAYamlChecker with the MCP extras, run the packaged `dayamlchecker-gen-mcp` command to generate a `.vscode/mcp.json` for the current workspace:

```bash
pip install "dayamlchecker[mcp]"
dayamlchecker-gen-mcp
```

Optional flags: `--venv <path>`, `--python <path>`, `--non-interactive`, and `--transport <stdio|sse|streamable-http>`.

### Alternative invocation (advanced / development)

If you're a developer or prefer not to install the package, you can run the generator script directly from the repo. This is useful if you want to test changes to the generator or use it without installing the package.

```bash
# Run using your local Python interpreter
python tools/generate_mcp_config.py --workspace . --non-interactive

# Run and point to a shared venv: good for users who keep venvs in ~/.venv
python tools/generate_mcp_config.py --venv ~/.venv --non-interactive

# Run with a specific python interpreter
python tools/generate_mcp_config.py --python /usr/bin/python3 --non-interactive
```

Advanced invocation examples:

```bash
# Use the installed CLI command instead of python -m
python tools/generate_mcp_config.py --command dayamlchecker-mcp --non-interactive

# Pass a JSON args array (useful for non-python `--command` and edge cases)
python tools/generate_mcp_config.py --command /usr/local/bin/python --args '["-m","dayamlchecker.mcp.server"]'
```

Advanced flags for the tools script (developer / debugging use):

* `--command <command>` — Use a custom command, e.g. `dayamlchecker-mcp` if you prefer to run the packaged CLI rather than `python -m` mode.
* `--args '<JSON array>'` — JSON array of args to pass to the command (e.g. `'[-m, "dayamlchecker.mcp.server"]'`).
* `--transport <stdio|sse|streamable-http>` — Select transport for MCP server.

The `tools/generate_mcp_config.py` script is a thin wrapper that calls `dayamlchecker.generate_mcp_config.main()` and is kept in the repo for contributors who prefer the convenience wrapper while developing or testing the generator.

#### Manual use of template mcp.json

This repository includes a `.vscode/mcp.json` configuration file. If you open this folder in VS Code, the editor can automatically detect and run the MCP server using the virtual environment.

1. **Ensure the virtual environment exists** in the project root (`.venv`) and the package is installed (see Installation above).
2. **Reload VS Code** or restart the MCP server if prompted.
3. **Open GitHub Copilot Chat**.
4. Look for the **attachment/tools icon** in the chat interface. You should see `dayamlchecker` or `validate_docassemble_yaml` available as a tool.

**How it works:**
The `.vscode/mcp.json` file tells VS Code to run the server using the python interpreter in your local `.venv`:

```json
{
  "servers": {
    "dayamlchecker": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "dayamlchecker.mcp.server"]
    }
  }
}
```

### Manual Configuration

If you prefer to configure the server globally or manually:

1. Install the package globally or in a central location.
2. Open VS Code Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`).
3. Select **"MCP: Manage MCP Servers"** (or edit your global user settings).
4. Add the following configuration:

    * **Type**: `stdio`
    * **Command**: `/path/to/python` (e.g., your venv python or global python)
    * **Args**: `["-m", "dayamlchecker.mcp.server"]`

## Running Locally & Debugging

You can run the server manually to test it or use the MCP Inspector.

### Using the MCP Inspector

The MCP Inspector is a web-based tool to test your server.

```bash
# Make sure you are in your venv
mcp dev dayamlchecker-mcp
```

This will launch a local web server where you can interactively call `validate_docassemble_yaml` with sample inputs.

### Running via Command Line

You can start the server directly (it communicates via stdin/stdout by default):

```bash
dayamlchecker-mcp
```

Or using python:

```bash
python -m dayamlchecker.mcp.server
```

## Other Integrations

### Gemini CLI

To use with Gemini's CLI or other tools that support MCP:

1. Start the server (usually via `mcp dev` or by configuring the client to spawn the process).
2. Refer to the specific client's documentation on how to register a `stdio` MCP server.

### OpenAI / HTTP-based Clients

If you need to expose the server via HTTP (SSE) for clients that don't support local process spawning:

```bash
mcp run -t sse python -m dayamlchecker.mcp.server
```

This will start an SSE transport that can be proxied to tools expecting an HTTP API.

### Codex (CLI / IDE) integration

Codex (both the CLI and the IDE extension) supports MCP servers and can be configured to use a local server you run on your machine.
The easiest way to add a stdio MCP server with the Codex CLI is the `codex mcp add` command.

Examples:

* Add `dayamlchecker` using the workspace `.venv` (run from the repo root):

```bash
codex mcp add dayamlchecker -- "$(pwd)/.venv/bin/python" -m dayamlchecker.mcp.server
```

* Add `dayamlchecker` using a global venv (`~/.venv`):

```bash
codex mcp add dayamlchecker -- "~/.venv/bin/python" -m dayamlchecker.mcp.server
```

* Add `dayamlchecker` using the installed CLI command (if installed globally):

```bash
codex mcp add dayamlchecker -- dayamlchecker-mcp
```

If you need to set environment variables, use `--env` flags before `--`, for example:

```bash
codex mcp add dayamlchecker --env EXAMPLE_VAR=foo -- "$(pwd)/.venv/bin/python" -m dayamlchecker.mcp.server
```

For a URL-based (SSE) server, add the server using the Codex config (or a CLI command that supports `--url`):

```toml
[mcp_servers.dayamlchecker]
url = "https://example.com/mcp"
bearer_token_env_var = "DAYAML_BEARER"
```

For more advanced options (timeouts, tool allow/deny lists, etc.), you can either pass flags to the `codex mcp add` command (if supported), or edit your `~/.codex/config.toml` manually with the `[mcp_servers.<server-name>]` table and the options shown earlier in this document.


## Tool Usage

The server exposes a single tool: `validate_docassemble_yaml`.

**Input:**

* `yaml_text` (string): The Docassemble YAML content to validate.

**Output:**

* A JSON object containing:
  * `valid` (boolean): True if valid, False otherwise.
  * `errors` (list): A list of error objects with `message`, `line`, and `filename`.

### Example Python Usage

You can import and use the validation logic directly in Python scripts without running the full server:

```python
from dayamlchecker.mcp.server import validate_docassemble_yaml

yaml_content = """
question: Hello
subquestion: |
  World
"""

result = validate_docassemble_yaml(yaml_content)
print(result)
```
