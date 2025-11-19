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

Important: Any VS Code click-to-install links or `.vscode/mcp.json` files only register configuration for the MCP server in VS Code. They do not create virtual environments or install the `dayamlchecker` package for you. Before using these UI actions, make sure the selected interpreter has `dayamlchecker` installed (for example: `python -m venv .venv && source .venv/bin/activate && pip install "dayamlchecker[mcp]"`).

### Alternative invocation (advanced / development)

If you're a developer or prefer not to install the package, you can copy and customize the mcp.json in .vscode/mcp.json
and edit manually to point to the path to the executable for this module.

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

* Add `dayamlchecker` using a global venv (`~/venv`):

```bash
codex mcp add dayamlchecker -- "~/venv/bin/python" -m dayamlchecker.mcp.server
```

* Add `dayamlchecker` using the installed CLI command (if installed globally):

```bash
codex mcp add dayamlchecker -- dayamlchecker-mcp
```

Note: If you have `dayamlchecker` installed in the same, activated virtual environment from which you're running the `codex mcp add` command (or if `dayamlchecker-mcp` is on the PATH for the user that runs Codex), you can use the short command `dayamlchecker-mcp` and do not need to pass an absolute path. If Codex or your Codex IDE is running outside the workspace or under a different process, prefer an absolute path to the Python executable or the CLI for reliability.

Important: `codex mcp add` only adds or registers the MCP server configuration in Codex's configuration; it does not create a venv or install Python packages. Make sure `dayamlchecker` is installed in the indicated interpreter before using the server.

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
