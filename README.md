# Ollama Web Search MCP

A small, resilient STDIO MCP server for Ollama Cloud's official Web Search and Web Fetch APIs.

It is designed for LiteLLM, Claude Desktop/Cowork, Codex, Cline, and other MCP clients.

## Tools

| Tool | Purpose |
|---|---|
| `web_search` | Search the public web and return up to 10 results. |
| `web_fetch` | Extract the main content and links from one public page. |
| `search_and_fetch` | Search, then fetch the top pages concurrently in one tool call. |

## Why this wrapper?

- Bounded retries for transient failures and rate limits
- Configurable timeouts
- Input and URL validation
- Partial success in `search_and_fetch`
- Safe error messages that do not expose the API key
- Small dependency surface, tests, and CI

## Requirements

- Python 3.11+
- An Ollama API key from [ollama.com](https://ollama.com)
- `uvx` (recommended) or `pip`

## Quick start

```bash
export OLLAMA_API_KEY="your-key"
uvx --from https://github.com/me3o2024/ollama-websearch-mcp/archive/refs/tags/v1.0.0.tar.gz ollama-websearch-mcp
```

## LiteLLM UI: STDIO configuration

Add a new MCP server and paste:

```json
{
  "mcpServers": {
    "ollama-websearch": {
      "command": "uvx",
      "args": [
        "--from",
        "https://github.com/me3o2024/ollama-websearch-mcp/archive/refs/tags/v1.0.0.tar.gz",
        "ollama-websearch-mcp"
      ],
      "env": {
        "OLLAMA_API_KEY": "your-ollama-api-key"
      }
    }
  }
}
```

Put the real key in `env`. `${OLLAMA_API_KEY}` is **not** expanded here — LiteLLM interpolates
`${...}` placeholders in HTTP headers, not in the `env` block of a stdio server. A placeholder is
passed to the subprocess verbatim, so the server sees the literal text `${OLLAMA_API_KEY}` and
fails with `OLLAMA_API_KEY is required`.

The LiteLLM container must have `uvx` installed and outbound HTTPS access to `ollama.com` and
`github.com`. The URL above is a source archive, which needs no `git` — see the note below if you
would rather install from a `git+https://` URL.

### Prefer a `git+https://` URL?

It works, but only where `git` is installed: `uvx` shells out to `git` to resolve it, and minimal
containers often ship without it. Either add git to the image:

```dockerfile
RUN apk add --no-cache git
```

or keep using the source-archive URL, which has no such dependency.

```text
git+https://github.com/me3o2024/ollama-websearch-mcp.git@v1.0.0
```

## Other MCP clients

```json
{
  "mcpServers": {
    "ollama-websearch": {
      "command": "uvx",
      "args": [
        "--from",
        "https://github.com/me3o2024/ollama-websearch-mcp/archive/refs/tags/v1.0.0.tar.gz",
        "ollama-websearch-mcp"
      ],
      "env": {
        "OLLAMA_API_KEY": "your-key"
      }
    }
  }
}
```

## Optional settings

| Variable | Default | Allowed |
|---|---:|---:|
| `OLLAMA_TIMEOUT_SECONDS` | `30` | Greater than 0, up to 300 |
| `OLLAMA_MAX_RETRIES` | `2` | 0 to 5 |

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

## Privacy

Search queries and URLs are sent from your MCP host to Ollama Cloud. The GitHub repository is only
the source of the code; it does not receive your searches. Do not place confidential information,
credentials, or customer data in web-search queries.

## API basis

This project uses Ollama's official endpoints:

- `POST https://ollama.com/api/web_search`
- `POST https://ollama.com/api/web_fetch`

See the [official Ollama Web Search documentation](https://docs.ollama.com/capabilities/web-search).

## License

MIT
