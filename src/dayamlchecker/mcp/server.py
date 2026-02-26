from typing import Any, Dict, List
from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from dayamlchecker.yaml_structure import find_errors_from_string

mcp = FastMCP("docassemble-yaml-checker")


@mcp.tool()
def validate_docassemble_yaml(yaml_text: str) -> Dict[str, Any]:
    """
    Validate a Docassemble interview YAML string using DAYamlChecker.

    This tool should be used whenever the model generates or modifies Docassemble YAML
    and needs to check for correctness, structure errors, or line-level issues.

    Args:
        yaml_text: The YAML content as a string.

    Returns:
        A dict with:
        - valid: bool
        - errors: list of structured errors (may be empty)
    """
    # Call the helper from DAYamlChecker
    result = find_errors_from_string(yaml_text)

    errors: List[Dict[str, Any]] = []

    for err in result:
        errors.append(
            {"message": err.err_str, "line": err.line_number, "filename": err.file_name}
        )

    valid = len(errors) == 0

    return {
        "valid": valid,
        "errors": errors,
    }


def main() -> None:
    """Entry point for running the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
