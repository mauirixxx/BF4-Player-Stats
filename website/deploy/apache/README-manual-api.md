# BF4PS manual request API: private gateway checklist

The existing leaderboard remains on `/bf4ps-api/` port 8765. The manual API binds to 127.0.0.1:8789 and is active in production.
The public entrypoint is the PHP file site/manual-gateway.php, not a direct
Apache proxy to port 8789. The configuration below records the original
predeployment gates; see docs/RELEASE-WEBSITE-2026-10-15.md for live state.

**Current Apache modules on tcou (2026-10-15):** proxy, proxy_http,
remoteip, rewrite and headers are enabled. `mod_evasive` and `mod_security`
were not present in the module inventory. Apache `mod_ratelimit` is not a
per-client request-count limiter; it throttles response bandwidth. Do not
use it as protection for this endpoint.

## Historical deployment gates (reviewed for production)

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

`manual-api-private.conf` is a **deny-only** placeholder, not the active
public gateway. Live requests are handled by site/manual-gateway.php; do not
install the placeholder as a substitute for the active configuration.
