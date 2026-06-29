# Security Policy

## Reporting a vulnerability

If you find a security issue, please do not open a public issue with exploit details.

For now, report vulnerabilities by opening a GitHub issue with a minimal description and asking for a private follow-up channel. Include enough context to reproduce the issue without sharing secrets.

## Secrets

Runtime credentials are expected to live only in deployment environments such as Render. Do not commit `.env` files, API keys, Spotify refresh tokens, Supabase service role keys, or other credentials to this repository.
