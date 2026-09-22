from __future__ import annotations

import pytest

from ollama_websearch_mcp import server
from ollama_websearch_mcp.client import OllamaAPIError


class FakeClient:
    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def web_search(self, query: str, max_results: int = 5) -> dict:
        return {
            "results": [
                {"title": "A", "url": "https://a.example", "content": query},
                {"title": "B", "url": "https://b.example", "content": str(max_results)},
            ]
        }

    async def web_fetch(self, url: str) -> dict:
        if url == "https://b.example":
            raise RuntimeError("page unavailable")
        return {"title": "A", "content": "page", "links": []}


@pytest.mark.asyncio
async def test_search_and_fetch_keeps_partial_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "OllamaWebClient", FakeClient)
    result = await server.search_and_fetch("query", max_results=2, fetch_top=2)

    assert len(result["results"]) == 2
    assert result["pages"][0]["ok"] is True
    assert result["pages"][1] == {
        "url": "https://b.example",
        "ok": False,
        "error": "page unavailable",
    }


@pytest.mark.asyncio
async def test_search_and_fetch_validates_fetch_top() -> None:
    with pytest.raises(ValueError, match="fetch_top"):
        await server.search_and_fetch("query", max_results=3, fetch_top=4)


@pytest.mark.asyncio
async def test_search_and_fetch_survives_ollama_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed fetch must degrade to ok=False, not abort the whole call.

    This is the real failure shape: OllamaWebClient wraps every transport
    error into OllamaAPIError before it reaches the tool.
    """

    class FailingClient(FakeClient):
        async def web_fetch(self, url: str) -> dict:
            if url == "https://a.example":
                raise OllamaAPIError("Ollama request failed after 3 attempt(s): RemoteProtocolError")
            return {"title": "B", "content": "page", "links": []}

    monkeypatch.setattr(server, "OllamaWebClient", FailingClient)
    result = await server.search_and_fetch("query", max_results=2, fetch_top=2)

    assert len(result["results"]) == 2
    assert result["pages"][0]["ok"] is False
    assert "RemoteProtocolError" in result["pages"][0]["error"]
    assert result["pages"][1]["ok"] is True
