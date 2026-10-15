# BF4PS manual request API: private gateway checklist

The existing leaderboard remains on `/bf4ps-api/` port 8765. The new manual
API binds to 127.0.0.1:8789 and is not started or publicly proxied.

**Current Apache modules on tcou (2026-10-15):** proxy, proxy_http,
remoteip, rewrite and headers are enabled. `mod_evasive` and `mod_security`
were not present in the module inventory. Apache `mod_ratelimit` is not a
per-client request-count limiter; it throttles response bandwidth. Do not
use it as protection for this endpoint.

## Deployment gates

1. Provision separate `bf4ps_manual_api` login with CONNECT, manual_api
   schema USAGE and approved function EXECUTE only. No direct table grants.
   The function owner must be NOLOGIN, SECURITY DEFINER with qualified SQL.
2. Verify a localhost-only authenticated smoke test, including forbidden
   direct SQL writes and request cooldown. No secret in source or Apache logs.
3. Select and test a real per-client rate limiter at the trusted public
   ingress (e.g. dedicated proxy with shared state), including correct
   handling of reverse proxy chains and spoofed `X-Forwarded-For` headers.
4. Add CSRF protection and strict Origin checks at the public ingress.
   Never embed `BF4PS_MANUAL_PRIVATE_TOKEN` in browser code, HTML or JS.
5. Bound total outstanding manual jobs and protect against distributed
   abuse, not just per-IP abuse. Test unknown-identity onboarding separately.
6. Only after all gates pass, add an explicitly reviewed public proxy
   route, enable systemd service, and enable the website buttons.

`manual-api-private.conf` is a **deny-only** placeholder, not an active
public proxy or rate limiter. No Apache configuration is modified by
checking these files into Git.