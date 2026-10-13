# v1.0.0 pending-release inventory

Status: **PENDING**, not tagged/released. Source: archive/pre-v1-soak-worktree-20261013.

## Required runtime
- `bf4ps/` production collector, persistence, discovery, request gate and scheduler modules. Phase-named modules must be dependency-reviewed before removing them.
- `migrations/`, `alembic.ini`, `pyproject.toml` (revisions 0001–0006).
- `scripts/bf4ps_production_collector.py`, `deploy/docker/`, Dockerfile.
- Canonical database schema documentation and operator runbook; regression tests kept in repository but excluded from image.

## Archived in Git history, excluded from Docker
- 153 experimental scripts, 50 phase/stage harness tests, and 5 experiment-only library modules removed from the release branch and preserved in `archive/pre-v1-soak-worktree-20261013` (commit `a028528`). Production-facing tests remain in `tests/`. Historical validation documentation remains accessible via the archive branch; curated operational documentation stays in release.
- Website/dashboard currently lives outside this repository on tcou; separately package and version it before production deployment.

## Release gates
1. Docker build and isolated smoke test; non-root runtime and credentials handling.
2. Stable configurable collector UUID/name/egress is implemented, preserving legacy host mappings. Verify fleet-wide UUID uniqueness and egress sharing under Docker; add collision protection acceptance tests.
3. Verify migrations against documented and live schemas; fresh install, upgrade, backup/restore and rollback procedure.
4. Document explicit discovery materialization/cutover, queue feeder and retry policy; test initial 191k-identity scale without a request storm.
5. Add health/readiness and restart/recovery checks, validate three-node Docker deployment.
6. Ensure frontend/API, country display, UCAV canonicalization, pagination, and DB connection configuration are versioned, tested and deployed as a separate website service.
7. Audit dependency pinning, image scanning, release notes, support matrix and operator procedures.

Do not drop D3. No database migration or collector restart is part of this repository-only staging change.
