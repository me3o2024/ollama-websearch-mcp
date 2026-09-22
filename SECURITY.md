# Security

## Reporting a vulnerability

Please open a private security advisory in GitHub instead of a public issue.

## Data handling

- Search queries and fetched URLs are sent to Ollama Cloud.
- The server does not intentionally log the API key or request content.
- Never include confidential tender content, credentials, or personal data in a search query.
- Keep `OLLAMA_API_KEY` in an environment variable. Never commit it to the repository.

## Supported versions

Security fixes are applied to the latest release.

