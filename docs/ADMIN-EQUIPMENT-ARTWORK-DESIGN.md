# Admin equipment artwork replacement — implementation contract (2026-10-16)

## Objective
The authenticated admin console can independently replace and restore **fancy** hero artwork and **HUD** thumbnails for every weapon and vehicle on `site/equipment.html`. Public users can only read images. Statistics and collectors are unaffected.

## Authoritative identity
Use `(kind, raw_key, role)` with `kind=weapon|vehicle`, stable `WARSAW_ID_...` raw key, and `role=fancy|hud`. Never key by display label or numeric catalog ID. Consult `docs/EQUIPMENT-SOURCE-OF-TRUTH.md` and `docs/catalog/equipment-artwork-manifest.json`. A missing original role is valid.

## Storage and publication
Use the canonical local filename from `site/equipment-artwork.js` in `/assets/equipment/`. Validate and transcode incoming PNG/JPEG/WebP to WebP. Before publishing or restoring, copy the current image to a timestamped backup under `/var/lib/bf4ps-admin/artwork/backups/` (outside the public webroot). Atomically replace the canonical file. Maintain private audit history; refresh browser image URLs with cache-busting query parameters. No public override manifest.

## Authentication
Reuse the existing loopback admin API and its session, Origin and CSRF checks; no second login. Read-only catalog/history endpoints and bounded authenticated upload/publish/restore endpoints. Validate the equipment key against server-side catalog allowlist. Never accept user-supplied filesystem paths. Restrict write access to upload directories, keep systemd filesystem protection. Audit actor, kind, key, role, action, time, digest and version. Do not log credentials or image contents.

## Interface
Add Equipment Artwork management in the existing admin console. Search equipment, show default and effective fancy/HUD side-by-side, independently select/preview files, publish explicitly, restore defaults and inspect version history. Clear errors and in-progress indicators.

## Release gates
Test auth, CSRF, Origin, invalid key/role, content spoofing, malformed/oversize/decompression bomb images, atomic updates, rollback and audit. Verify moderation and password changes still work. Deploy without altering any current artwork; test one approved weapon and vehicle across both roles, then restore. Verify cache refresh, public equipment page, leaderboard API and collectors. Maintain rollback to original public page and timestamped artwork backups.
