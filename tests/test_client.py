from __future__ import annotations

import httpx
import pytest

from ollama_websearch_mcp.client import (
    OllamaAPIError,
    OllamaWebClient,
    validate_max_results,
    validate_query,
    validate_url,
)


def test_validators_accept_normal_input() -> None:
    assert validate_query("  ollama cloud  ") == "ollama cloud"
    assert validate_max_results(10) == 10
    assert validate_url("https://example.com/page") == "https://example.com/page"


@pytest.mark.parametrize("query", ["", "   ", "x" * 501])
def test_query_rejects_invalid_input(query: str) -> None:
    with pytest.raises(ValueError):
        validate_query(query)


@pytest.mark.parametrize("value", [0, 11, True, 1.5])
def test_max_results_rejects_invalid_input(value: object) -> None:
    with pytest.raises(ValueError):
        validate_max_results(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:pass@example.com",
        "http://localhost/admin",
        "http://127.0.0.1",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_url_rejects_unsafe_input(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.asyncio
async def test_web_search_returns_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"results": [{"title": "Ollama", "url": "https://ollama.com", "content": "x"}]},
        )

    async with OllamaWebClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.web_search("ollama", 1)

    assert response["results"][0]["title"] == "Ollama"


@pytest.mark.asyncio
async def test_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def no_sleep(_: float) -> None:
        return None

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": "slow down"}, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr("ollama_websearch_mcp.client.asyncio.sleep", no_sleep)
    async with OllamaWebClient(
        api_key="test-key",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert await client.web_search("ollama") == {"results": []}
    assert calls == 2


@pytest.mark.asyncio
async def test_safe_api_error_does_not_expose_key() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid token"})

    async with OllamaWebClient(
        api_key="super-secret",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(OllamaAPIError, match="invalid token") as exc_info:
            await client.web_search("ollama")
    assert "super-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_invalid_json_is_reported_cleanly() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    async with OllamaWebClient(
        api_key="test-key",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(OllamaAPIError, match="invalid JSON"):
            await client.web_search("ollama")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        httpx.RemoteProtocolError("server disconnected mid-response"),
        httpx.LocalProtocolError("bad frame"),
        httpx.ProxyError("proxy refused"),
        httpx.ReadTimeout("read timed out"),
        httpx.ConnectError("connection refused"),
    ],
)
async def test_transport_errors_become_safe_api_errors(
    monkeypatch: pytest.MonkeyPatch, error: httpx.TransportError
) -> None:
    """Any transport failure must surface as OllamaAPIError, never a raw httpx error.

    Regression: the handler previously caught only TimeoutException and
    NetworkError, so ProtocolError (a sibling, not a subclass) escaped and
    aborted callers that expect a clean, catchable failure.
    """

    async def no_sleep(_: float) -> None:
        return None

    async def handler(_: httpx.Request) -> httpx.Response:
        raise error

    monkeypatch.setattr("ollama_websearch_mcp.client.asyncio.sleep", no_sleep)
    async with OllamaWebClient(
        api_key="test-key",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(OllamaAPIError, match="attempt"):
            await client.web_search("ollama")


@pytest.mark.parametrize("value", [0, 0.0, -1, 301])
def test_timeout_seconds_out_of_range_is_rejected(value: float) -> None:
    """0 must be rejected, not silently replaced by the default.

    Regression: `timeout_seconds or _float_env(...)` treated 0 as falsy and
    fell back to 30, so the documented lower bound was never enforced.
    """
    with pytest.raises(OllamaAPIError, match="OLLAMA_TIMEOUT_SECONDS"):
        OllamaWebClient(api_key="test-key", timeout_seconds=value)


def test_timeout_seconds_zero_via_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "0")
    with pytest.raises(OllamaAPIError, match="OLLAMA_TIMEOUT_SECONDS"):
        OllamaWebClient(api_key="test-key")

