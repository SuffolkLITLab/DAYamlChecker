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
