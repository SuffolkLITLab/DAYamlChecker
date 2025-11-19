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

To make it easy for VS Code users to install locally, install DAYamlChecker with the `mcp` extra, then run the packaged generator to create `.vscode/mcp.json`:

```bash
# Install in the active environment
pip install "dayamlchecker[mcp]"

# Generate workspace MCP config
dayamlchecker-gen-mcp
```

Optional flags: `--venv <path>`, `--python <path>`, and `--non-interactive`.

For example, if you have a global venv in ~/venv, and a github repository
you want to make the MCP available in named docassemble-AssemblyLine:

```bash
cd ~/docassemble-AssemblyLine
source ~/venv/bin/activate
pip install dayamlchecker[mcp]
dayamlchecker-gen-mcp --venv ~/venv
```

### Codex CLI (optional)

If you use Codex CLI/IDE and want Codex to call this MCP server:

```bash
cd /path/to/your/repo
codex mcp add dayamlchecker -- "$(pwd)/.venv/bin/python" -m dayamlchecker.mcp.server

# Or add using a global venv
codex mcp add dayamlchecker -- "~/.venv/bin/python" -m dayamlchecker.mcp.server

# If the package is installed globally
codex mcp add dayamlchecker -- dayamlchecker-mcp
```
