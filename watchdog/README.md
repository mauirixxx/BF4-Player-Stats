# BF4PS infrastructure watchdog (planned)

`admins.json` is the initial **configuration**, not an active notifier. It lists the confirmed private alert channel and all configured infrastructure administrators. The watchdog is not deployed yet.

The Discord snowflake `discord_user_id` is the immutable routing key. `username` and `display_name` are human-readable labels, not authorization inputs. The first name was supplied by the operator; the second account name must be resolved through the authenticated Discord bot/API before it is displayed as verified. Refresh names on startup and periodically, record `last_verified_at`, and preserve the previous known label on temporary API failure. Never overwrite a valid name with a guess or rely on names for authorization. Do not publish bot credentials or private contact information here.

Send every OPEN, ESCALATED and RECOVERED event to the configured channel **and** DM every enabled admin. A failed DM must not prevent other deliveries. Any admin changes must be audited and require authenticated management access. See `docs/INFRASTRUCTURE-WATCHDOG-DESIGN.md`.
