# Hermes deployment and integrations

Hermes Orakel is the separately deployed assistant gateway used with Personal.
This document records the production boundary so the application and its
operators agree on which configuration belongs in this repository and which
configuration belongs in Azure and Hermes.

## Azure model deployment

The active Azure AI Foundry deployment is:

| Setting | Value |
| --- | --- |
| Resource | `kvarteret-nor-east-resource` |
| Region | Norway East |
| Deployment | `hermes-gpt-5-6-luna` |
| Model | `gpt-5.6-luna` |
| Deployment type | Global Standard |
| Provisioning state | Succeeded |
| Tokens/minute | 200,000 |
| Requests/minute | 200 |

The endpoint and API key are runtime secrets/configuration. They must be
stored in the Hermes host's secret store and must not be committed here.
Quota changes are made in Azure AI Foundry and should be reflected in this
record after verification.

## Authentication boundary

Personal remains the system of record for user identity and authorization.
Supabase Auth authenticates users, while the shared parent-domain session
cookie allows the Personal and Orakel subdomains to reuse the authenticated
session. The cookie domain is configured with `SESSION_COOKIE_DOMAIN`; it must
be restricted to the intended parent domain and must use secure, HTTP-only
cookie settings in production.

`app/web/cookies.py` only attaches `SESSION_COOKIE_DOMAIN` when the request
host is that domain or a subdomain of it. The same application is also served
on the `personal.kvarteret.no` alias, which is outside the
`samfunnetibergen.no` parent domain; there the browser would reject the shared
cookie, so it falls back to a host-only cookie. Cross-domain single sign-on
between Personal and Orakel therefore requires users to land on
`personal.samfunnetibergen.no`, not the `kvarteret.no` alias.

Hermes must validate the Personal session before serving the web UI or
forwarding a user request to an MCP integration. Hermes does not create a
second user directory and must not accept an Entra-only identity as a
substitute for Personal authentication.

## MCP integrations

The following integrations are connected to Hermes as MCP capabilities:

- Crescat, for the existing booking/operations integration.
- PostHog, for analytics and diagnostics queries.
- Sanity, for content and event data.
- Slack, through the Hermes Slack gateway. Slack access is restricted to the
  approved Slack user IDs configured in Hermes; tokens are stored only as
  secrets.

The Personal application continues to use its own direct adapters where
documented in [External systems](external-systems.md). Hermes MCP access is a
separate gateway capability and should not be treated as an authorization
grant to Personal APIs.

## Operational checklist

When changing the deployment or gateway:

1. Verify the Azure deployment is `Succeeded` and record its current quota.
2. Keep Azure keys, Supabase secrets, OAuth credentials, and Slack tokens out
   of Git, logs, and PR descriptions.
3. Verify Personal login and the Orakel return URL on both subdomains.
4. Verify each MCP integration with a least-privilege test account.
5. Re-run the Personal test suite and deploy the approved branch through the
   normal Vercel release process.
