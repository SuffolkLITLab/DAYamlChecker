# DAYamlChecker

An LSP for Docassemble YAML Interviews

## How to run

```bash
pip install .
python3 -m dayamlchecker `find . -name "*.yml" -path "*/questions/*" snot -path "*/.venv/*" -not -path "*/build/*"` # i.e. a space separated list of files
```

## MCP / LLM integration

DAYamlChecker includes an optional Model Context Protocol (MCP) server. This allows AI assistants like GitHub Copilot to validate Docassemble YAML directly within your editor.

### Quick Start

1. **Install with MCP support:**

   ```bash
   pip install "dayamlchecker[mcp]"
   ```

2. **VS Code Automatic Setup:**
   Open this project in VS Code. The included `.vscode/mcp.json` file will automatically configure the MCP server for you (assuming you have a `.venv` created).

For detailed instructions on installation, manual configuration, and usage with other clients, please see [docs/MCP_SERVER.md](docs/MCP_SERVER.md).

### Generate a VS Code MCP configuration

To make it easy for VS Code users to install locally, there's a helper script included in `tools/` that will create a `.vscode/mcp.json` for the current workspace. It detects a local `.venv` by default or you can specify a custom venv or python path.

```bash
# Use the auto-detect .venv behavior
python tools/generate_mcp_config.py

# Use a specific venv located in ~/.venv
python tools/generate_mcp_config.py --venv ~/.venv

# Use a specific interpreter directly
python tools/generate_mcp_config.py --python /usr/bin/python3
```

If you want to avoid the interactive prompts, add `--non-interactive` to use the detected values.

If you installed the package (`pip install "dayamlchecker[mcp]"`) you can also use the installed console script:

```bash
# If the package is installed, and you want to run as a command
dayamlchecker-gen-mcp
```

