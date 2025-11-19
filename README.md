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
codex mcp add dayamlchecker -- "~/venv/bin/python" -m dayamlchecker.mcp.server
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
codex mcp add dayamlchecker -- "~/venv/bin/python" -m dayamlchecker.mcp.server

# If the package is installed globally
codex mcp add dayamlchecker -- dayamlchecker-mcp
```

### Click-to-install for VS Code

If you want VS Code users to add the MCP server with a single click, include one of the links below. These open VS Code and pre-fill the Add MCP Server dialog. They rely on an interpreter being present at the configured path — the local link expects a repository `.venv` and the global link expects a global venv such as `~/venv`.


[Add dayamlchecker (workspace .venv)](vscode:mcp/install?%7B%22name%22%3A%22dayamlchecker%22%2C%22type%22%3A%22stdio%22%2C%22command%22%3A%22%24%7BworkspaceFolder%7D%2F.venv%2Fbin%2Fpython%22%2C%22args%22%3A%5B%22-m%22%2C%22dayamlchecker.mcp.server%22%5D%7D)

 Click to add a server that uses a global `~/venv`:
 
[Add dayamlchecker (global ~/venv)](vscode:mcp/install?%7B%22name%22%3A%22dayamlchecker%22%2C%22type%22%3A%22stdio%22%2C%22command%22%3A%22~%2Fvenv%2Fbin%2Fpython%22%2C%22args%22%3A%5B%22-m%22%2C%22dayamlchecker.mcp.server%22%5D%7D)
 

Note: Some clients may not expand `~`, so replace it with the absolute path if the link doesn't work for you (e.g. `/home/yourname/venv/bin/python`). Also ensure the package is installed in the selected venv (`pip install "dayamlchecker[mcp]"`), and the `.venv` path exists with a Python binary.

Note: If you have `dayamlchecker` installed in the same, activated virtual environment from which you're running the `codex mcp add` command (or if `dayamlchecker-mcp` is on the PATH for the user that runs Codex), you can use the short command `dayamlchecker-mcp` and do not need to pass an absolute path. If Codex or your Codex IDE is running outside the workspace or under a different process, prefer an absolute path to the Python executable or the CLI for reliability.
