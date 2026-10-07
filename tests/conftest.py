import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))



@pytest.fixture(scope="session", autouse=True)
def dictionary_cache(request):
    """Keep downloaded dictionaries in pytest's cache, so local runs fetch once."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(
            "DAYAMLCHECKER_CACHE_DIR", str(request.config.cache.mkdir("dayamlchecker"))
        )
        yield


@pytest.fixture
def requires_spanish():
    """Fetch the Spanish dictionary; skip when offline, except in CI."""
    from dayamlchecker.spelling import _remote_dictionary_prefix

    try:
        _remote_dictionary_prefix("es")
    except ValueError as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Spanish dictionary unavailable: {exc}")
