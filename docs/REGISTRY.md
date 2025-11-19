# Publishing DAYamlChecker to the MCP Registry

This page shows how to prepare DAYamlChecker for listing on the GitHub MCP Registry and how to submit it.

TL;DR: MCP registry listings are not generated from PyPI — you must provide a server metadata description (JSON or YAML), a public repository, and follow the registry submission process (PR or web form) to add the server to the MCP registry.

## What you need

- A public GitHub repository (this repo qualifies).
- A release (tag / GitHub release) that corresponds to your server's metadata `version` attribute.
- A `mcp-server.json` metadata file in the repository (example included in the repo root).
- A console script to run the MCP server, or an HTTP mountable server (we provide `dayamlchecker-mcp`).
- A LICENSE and README with install instructions (we already include these).
- (Optional) Icon file (e.g., `assets/lit-favicon.svg`) for UX in the registry.

## Sample `mcp-server.json`

We've added an example `mcp-server.json` at the project root. It contains fields typically used by MCP registries:

```json
{
  "name": "dayamlchecker",
  "title": "DAYamlChecker YAML Validator – MCP Server",
  "description": "A tool for validating Docassemble YAML interviews via MCP.",
  "version": "0.2.0",
  "transport": "stdio",
  "command": "dayamlchecker-mcp",
  "args": [],
  "icon": "assets/lit-favicon.svg",
  "repository": "https://github.com/SuffolkLITLab/DAYamlChecker",
  "license": "MIT",
  "publisher": "SuffolkLITLab"
}
```

### Notes on fields

- `transport`: `stdio`, `sse`, or `streamable-http` (follow FastMCP's supported options).
- `command`: the CLI command that starts the server (must be installed via `pip install`). In our case `dayamlchecker-mcp`.
- `repository`: URL of your repo hosting the project.
- `version`: a semver-like string that matches a tagged GitHub release.
- `icon`: optional path that should exist in the repository (recommended for registry UX).

## How to publish

1. Make sure the server works locally and has `mcp-server.json` and `assets/lit-favicon.svg` (optional) committed.
2. Tag a release on GitHub (e.g., `git tag v0.2.0 && git push --tags`) and create a release with release notes.
3. Optionally, publish a PyPI release (not required for registry, but recommended): `python -m build` and `twine upload dist/*`.

### Add the server to the registry

The MCP Registry (hosted on GitHub) is community-run. There are two common ways to add an entry:

- Open a Pull Request in the MCP registry `servers` repo ([https://github.com/mcp/servers](https://github.com/mcp/servers)) adding your metadata or reference to your server.
- Use a web-based submission UI if one exists (or a web form maintained by the MCP org). If the registry accepts web submissions, follow the UI instructions and provide the link to your `mcp-server.json` (or paste the metadata).

In your PR or submission, include:

- A metadata file (or a pointer to one in your repo).
- Repo link and a small blurb/title that will show up in VS Code and gallery listings.
- `license` and `publisher` information.
- An `assets/lit-favicon.svg` or similar image if you want a visual in the listing.
- A short README snippet on how to install it (`pip install "dayamlchecker[mcp]"`) and how to configure VS Code (e.g., `code --add-mcp` or `.vscode/mcp.json`).

### Example PR steps

1. Fork `https://github.com/mcp/servers` to your GitHub account.
2. Create a new file under `catalog/` or follow the repo pattern (check the existing servers), e.g., `catalog/io.github.suffolklitlab.dayamlchecker.json`.
3. Add the minimal JSON metadata in a new file. Example name pattern: `catalog/<owner>.<repo>.json`.
4. Add the server name, version, and icon fields and the `repository` URL.
5. Add a short summary description for the catalog.
6. Open a PR and request a review — mention the MCP maintainers and link to your server repository.
7. After approval, your server will be shown in the MCP Registry & will become installable via the MCP registry UI in clients like VS Code or Copilot.

## Post-publishing checklist

- Verify the server shows up in VS Code's MCP Servers panel (try `mcp dev` before if needed).
- Verify the `validate_docassemble_yaml` tool is displayed and callable.
- Optionally provide example requests in your README for users and integration tests.

## Helpful tips

- If your server uses `stdio`, make sure `dayamlchecker-mcp` CLI is installed with the `mcp` extra.
- If you provide a `streamable-http` server, include URL examples and CORS configuration notes.
- Use a semver tag so users know release compatibility.
- Add a `mcp-server.json` in the repo root to make it easier for registry maintainers to build a listing.

## Where to find registry documentation

- Check the MCP GitHub org and the `mcp` repos for servers/catalog guidance ([https://github.com/mcp](https://github.com/mcp)).
- If the registry uses the GitHub `mcp` org `servers` repository for listings (common pattern), check their README for contribution guidelines.

*** End Patch