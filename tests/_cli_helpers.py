from dataclasses import dataclass


@dataclass
class RunResult:
    """Shared helper capturing CLI invocation results for tests."""

    returncode: int
    stdout: str
    stderr: str
