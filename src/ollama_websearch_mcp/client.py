"""Resilient async client for the Ollama Cloud web APIs."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import random
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

OLLAMA_BASE_URL = "https://ollama.com"
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class OllamaAPIError(RuntimeError):
    """A safe, user-facing Ollama API error."""


def require_api_key() -> str:
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if not api_key:
        raise OllamaAPIError("OLLAMA_API_KEY is required")
    return api_key


def validate_query(query: str) -> str:
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    if len(query) > 500:
        raise ValueError("query must be 500 characters or fewer")
    return query


def validate_max_results(max_results: int) -> int:
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise ValueError("max_results must be an integer")
    if not 1 <= max_results <= 10:
        raise ValueError("max_results must be between 1 and 10")
    return max_results


def validate_url(url: str) -> str:
    url = url.strip()
    if not url or len(url) > 2048:
        raise ValueError("url must be between 1 and 2048 characters")

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be an absolute http or https URL")
    if parsed.username or parsed.password:
        raise ValueError("url must not contain embedded credentials")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("localhost URLs are not allowed")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("private, loopback, and reserved IP addresses are not allowed")
    return url


class OllamaWebClient:
    """Minimal Ollama Cloud client with bounded retries and safe errors."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = OLLAMA_BASE_URL,
    ) -> None:
        self.api_key = api_key or require_api_key()
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _float_env("OLLAMA_TIMEOUT_SECONDS", 30.0)
        )
        self.max_retries = (
            max_retries if max_retries is not None else _int_env("OLLAMA_MAX_RETRIES", 2)
        )
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise OllamaAPIError("OLLAMA_TIMEOUT_SECONDS must be between 0 and 300")
        if not 0 <= self.max_retries <= 5:
            raise OllamaAPIError("OLLAMA_MAX_RETRIES must be between 0 and 5")

        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "ollama-websearch-mcp/1.0.0",
            },
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=transport,
        )

    async def __aenter__(self) -> OllamaWebClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def web_search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        payload = {
            "query": validate_query(query),
            "max_results": validate_max_results(max_results),
        }
        data = await self._post("/api/web_search", payload)
        results = data.get("results")
        if not isinstance(results, list):
            raise OllamaAPIError("Ollama returned an unexpected web_search response")
        return data

    async def web_fetch(self, url: str) -> dict[str, Any]:
        data = await self._post("/api/web_fetch", {"url": validate_url(url)})
        if not isinstance(data.get("content"), str):
            raise OllamaAPIError("Ollama returned an unexpected web_fetch response")
        return data

    async def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(path, json=payload)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    attempts = attempt + 1
                    error_name = type(exc).__name__
                    raise OllamaAPIError(
                        f"Ollama request failed after {attempts} attempt(s): {error_name}"
                    ) from None
                await asyncio.sleep(_backoff_seconds(attempt, None))
                continue

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                await asyncio.sleep(
                    _backoff_seconds(attempt, response.headers.get("Retry-After"))
                )
                continue

            if response.is_error:
                message = _safe_error_message(response)
                raise OllamaAPIError(f"Ollama API error {response.status_code}: {message}")

            try:
                data = response.json()
            except ValueError:
                raise OllamaAPIError("Ollama returned invalid JSON") from None
            if not isinstance(data, dict):
                raise OllamaAPIError("Ollama returned an unexpected response")
            return data

        raise OllamaAPIError("Ollama request failed")  # pragma: no cover


def _safe_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.reason_phrase or "request failed"

    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    return response.reason_phrase or "request failed"


def _backoff_seconds(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), 30.0)
        except ValueError:
            pass
    return min(0.5 * (2**attempt) + random.uniform(0.0, 0.25), 5.0)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        raise OllamaAPIError(f"{name} must be a number") from None


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        raise OllamaAPIError(f"{name} must be an integer") from None
