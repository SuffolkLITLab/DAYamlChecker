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

#### Convenience script: generate `.vscode/mcp.json`

To make it easy for VS Code users to wire up the MCP server, there's a helper script at `tools/generate_mcp_config.py` in the project. It:

* Detects a local `.venv` in your repository root and uses that interpreter by default.
* Lets you specify a `--venv` directory or a `--python` path to an arbitrary interpreter.
* Lets you override the command (e.g. `dayamlchecker-mcp`) or use the default `python -m dayamlchecker.mcp.server` which is the most portable choice.
* By default it writes the config with a `stdio` transport. You can specify `--transport sse` for SSE mode.

Run the script from the workspace root (or pass `--workspace`):

```bash
# Use the default local .venv if present
python tools/generate_mcp_config.py

# Or specify a venv path (e.g., tildes are supported):
python tools/generate_mcp_config.py --venv ~/.venv

# Or specify a python interpreter explicitly
python tools/generate_mcp_config.py --python /usr/bin/python3
```

Common example for users who keep a reusable venv in `~/.venv`:

```bash
python tools/generate_mcp_config.py --venv ~/.venv
```

The script writes `.vscode/mcp.json` and prints follow-up instructions to open the project in VS Code. You can use `--non-interactive` if you do not want to be prompted.

If you installed the package in your environment, you can also run the packaged console script:

```bash
dayamlchecker-gen-mcp
```

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
