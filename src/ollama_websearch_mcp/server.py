"""MCP tools for Ollama Cloud web search."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import OllamaWebClient, validate_max_results

mcp = FastMCP("ollama-websearch")


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the public web with Ollama Cloud.

    Args:
        query: A concise search query. Do not include secrets or confidential data.
        max_results: Number of results to return, from 1 to 10.
    """
    async with OllamaWebClient() as client:
        return await client.web_search(query, max_results)


@mcp.tool()
async def web_fetch(url: str) -> dict[str, Any]:
    """Fetch and extract the main content of one public HTTP(S) web page.

    Args:
        url: Absolute public HTTP or HTTPS URL to fetch.
    """
    async with OllamaWebClient() as client:
        return await client.web_fetch(url)


@mcp.tool()
async def search_and_fetch(
    query: str,
    max_results: int = 5,
    fetch_top: int = 3,
) -> dict[str, Any]:
    """Search the web and fetch the top results in one call.

    This convenience tool reduces agent round trips. Individual fetch failures are
    returned beside successful pages instead of failing the whole operation.

    Args:
        query: A concise search query. Do not include secrets or confidential data.
        max_results: Number of search results to return, from 1 to 10.
        fetch_top: Number of top result pages to fetch, from 1 to max_results.
    """
    max_results = validate_max_results(max_results)
    if isinstance(fetch_top, bool) or not isinstance(fetch_top, int):
        raise ValueError("fetch_top must be an integer")
    if not 1 <= fetch_top <= max_results:
        raise ValueError("fetch_top must be between 1 and max_results")

    async with OllamaWebClient() as client:
        search_response = await client.web_search(query, max_results)
        results = search_response.get("results", [])
        urls = [item.get("url") for item in results[:fetch_top] if isinstance(item, dict)]

        async def fetch_one(url: object) -> dict[str, Any]:
            if not isinstance(url, str):
                return {"url": url, "ok": False, "error": "search result has no valid URL"}
            try:
                page = await client.web_fetch(url)
                return {"url": url, "ok": True, "page": page}
            except (RuntimeError, ValueError) as exc:
                return {"url": url, "ok": False, "error": str(exc)}

        pages = await asyncio.gather(*(fetch_one(url) for url in urls))
        return {"query": query.strip(), "results": results, "pages": pages}


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

