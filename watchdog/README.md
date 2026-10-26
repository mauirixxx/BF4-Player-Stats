# BF4PS infrastructure watchdog (planned)

`admins.json` is the initial **configuration**, not an active notifier. It lists the confirmed private alert channel and all configured infrastructure administrators. The watchdog is not deployed yet.

The Discord snowflake `discord_user_id` is the immutable routing key. `username` and `display_name` are human-readable labels, not authorization inputs. The first name was supplied by the operator; the second account name must be resolved through the authenticated Discord bot/API before it is displayed as verified. Refresh names on startup and periodically, record `last_verified_at`, and preserve the previous known label on temporary API failure. Never overwrite a valid name with a guess or rely on names for authorization. Do not publish bot credentials or private contact information here.

Send every OPEN, ESCALATED and RECOVERED event to the configured channel **and** DM every enabled admin. A failed DM must not prevent other deliveries. Any admin changes must be audited and require authenticated management access. See `docs/INFRASTRUCTURE-WATCHDOG-DESIGN.md`.

## First implementation (2026-10-26)

`watchdog.py` is a one-shot probe invoked by `bf4ps-watchdog.timer`. Its first run establishes a baseline without paging; three consecutive failed checks trigger an OPEN alert, and recovery triggers a RECOVERED alert. State is persisted at `/var/lib/bf4ps-watchdog/state.json`. It checks five PostgreSQL nodes via SSH (service + root filesystem), nine worker hosts via SSH TCP reachability, the mak-01 local Docker containers and systemd services, the website homepage, and the mak-01 root filesystem. Disk warning threshold is 80% or less than 5 GiB free. Discord delivery uses the existing private bot token on mak-01, sends to the configured channel and opens individual DMs to every enabled admin; failures are logged separately. `python3 watchdog.py --test` sends an explicitly marked test to all destinations. This is **initial coverage**, not yet exhaustive per-node service monitoring or HA monitoring. It does not yet provide escalation, sustained reminder alerts, or remote worker service-level probes; expand in subsequent milestones. Never claim a node's services are healthy based on its SSH port alone.

## Discord alert presentation

Incident and recovery notifications use short multiline Markdown messages with severity, friendly service name, node, status, and detection/recovery time in Hawaii Standard Time (UTC−10). Filesystem alerts also show percent used and GiB free. Raw PostgreSQL paths and internal command output are not included in messages. This formatting change does not resend already-open incidents; only newly opened or recovered incidents trigger alerts.

Ranking progress check: watchdog queries the production queue via mak-db-02's local postgres account over authenticated SSH. An unhealthy ranking gate, unavailable telemetry, or a due backlog with no active job and no successful completion in 20 minutes triggers the existing three-failed-check alert policy. This checks real progress rather than only Docker process state; prolonged active jobs still need additional timeout telemetry.

### Platoon processing checks

Read-only production PostgreSQL checks independently monitor (1) last successful platoon refresh (alert when no success for 20 minutes while work is due), and (2) oldest due platoon refresh (alert when due for 24 hours). They include due count, active lease count and failed request count in diagnostic details. Both use the standard three consecutive failed probes, channel + admin DMs, and recovery messages. SSH port availability is **not** a remote systemd service check. Individual service failure-count monitoring on mak-05 and hnl-03 remains a follow-up because mak-01 cannot currently authenticate over SSH to those nodes; do not silently assume it is covered.

### Remote worker service probes (mak-05, hnl-03)

A dedicated `bf4ps-watchdog-platoon` SSH key on mak-01 is authorized on each worker only with `restrict,command="/usr/local/sbin/bf4ps-platoon-health"` (no forwarding, PTY or arbitrary commands). The helper script is tracked in `watchdog/remote/bf4ps-platoon-health`. It returns JSON with timer activity, recent failures and successes from a bounded five-minute/150-line journal sample. Alert if timer is inactive or at least three recent failures are observed, subject to the global three consecutive watchdog checks. This supplements, not replaces, the database-level progress and queue-age checks. The journal sample is bounded and may miss failures during extremely verbose logging; a dedicated durable failure counter would improve accuracy.
