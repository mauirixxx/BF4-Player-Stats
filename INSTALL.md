# BF4PS installation and deployment guide

**Release state:** consolidated source, **not yet verified as a clean production installation**. This guide identifies the component entry points and safety gates. Do not aim an untested checkout at an existing production database.

## Requirements and boundaries

- Linux host(s) with Python 3.12+, PostgreSQL accessible over a private network, and optionally Docker Compose for the player collector.
- Apache/PHP for the public site. Python APIs and background exports are separate services; the HTML directory alone is not a functional deployment.
- A dedicated BF4PS database, a least-privileged website account, and a separate **read-only** account for any BF4 Server Watcher discovery source.
- Stable, unique collector UUID/name per worker; workers sharing an egress budget use the same `BF4PS_EGRESS_KEY`.
- Keep credentials, `.env` files, backup data, generated JSON, images fetched at runtime, and local systemd overrides **outside** the repository.

## Obtain source

```sh
git clone https://github.com/mauirixxx/BF4-Player-Stats.git
cd BF4-Player-Stats
```

The layout is `website/`, `player-collector/`, `platoon-collector/`, `discord-bot/` (future), and `docs/`. Consult [README.md](README.md) for component responsibilities.

## Player collector (Docker example)

```sh
cd player-collector
cp deploy/docker/discovery.env.example deploy/docker/discovery.env
cp deploy/docker/collector.env.example deploy/docker/collector.env
# Edit both local files with real credentials and a unique worker identity.
docker compose -f deploy/docker/compose.yaml build
```

**Do not run the following migration command until the database is isolated, the URL has been reviewed, and a backup/restore plan is verified.** The authoritative Alembic chain is `0001`–`0017`; schema contracts are in [docs/database-schema-reference.md](docs/database-schema-reference.md). From `player-collector/`, the intended migration invocation is:

```sh
docker compose -f deploy/docker/compose.yaml run --rm discovery alembic upgrade head
```

The Compose definition has no bundled PostgreSQL. After migration verification, explicitly enable the appropriate discovery/collector services. Do not enable job materialization or increase collection traffic merely by following this guide. See [player-collector/deploy/docker/README.md](player-collector/deploy/docker/README.md).

## Website

- Serve `website/site/` as the document root through Apache/PHP, with an HTTPS virtual host and the project's expected URL routes.
- Deploy `website/api/` privately with an isolated Python environment and a least-privileged DB connection. The public site expects `/bf4ps-api/` routes; a static-file server will not satisfy them.
- `website/site/manual-gateway.php` is the manual-request public entry point. Read [website/deploy/apache/README-manual-api.md](website/deploy/apache/README-manual-api.md) before enabling it. The provided `manual-api-private.conf` is a deny-only placeholder, **not** a ready-made public proxy configuration.
- Inspect `website/deploy/systemd/` and adjust absolute paths, service users, file permissions, database accounts and environment paths to the target host. Do not copy production credentials.

**Not supplied as a turnkey installer:** complete Apache vhost and URL-routing configuration, production database role provisioning, full website dependency lockfiles, and a verified fresh-host service bootstrap. These must be finished and tested before declaring one-command deployment.

## Platoon collector

The production scripts are under `platoon-collector/scripts/`. Read [platoon-collector/README.md](platoon-collector/README.md) for timer semantics, matching-script hash verification and safe rolling deployment. A complete portable platoon service installer is not yet provided. Do not assume the unrelated homepage-summary timer in `platoon-collector/deploy/systemd/` installs the platoon scheduler.

## Discord bot

`discord-bot/` contains a future component placeholder only; no runnable bot is included.

## Required release gates

1. Clean isolated PostgreSQL migration rehearsal through `0017`, followed by catalog comparison with the documented live schema.
2. Clean-host build/startup tests for every shipped component; validate website API routes and runtime dependencies.
3. Verify source parity against live deployed website and player collector, not only the platoon workers.
4. Verify least privilege, secret handling, health checks, backups, restart behavior and rollback.
5. Publish exact tested versions and deployment commands after those gates pass.

The historical test inventory and **actual** validation results are in [docs/TEST-AND-VALIDATION-HISTORY.md](docs/TEST-AND-VALIDATION-HISTORY.md). A removed historical test is not a passed current test.
