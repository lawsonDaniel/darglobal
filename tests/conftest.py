import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODELS", "first:free,second:free")
for k in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY", "SEARCH_PROVIDER"):
    os.environ.pop(k, None)

import pytest  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"
