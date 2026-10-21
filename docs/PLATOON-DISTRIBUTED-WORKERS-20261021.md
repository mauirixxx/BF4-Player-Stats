# BF4PS distributed platoon workers

Production rollout remains staged. The existing mak-05 worker uses atomic PostgreSQL UPDATE RETURNING with FOR UPDATE SKIP LOCKED for platoon and discovery jobs. This is not yet token-fenced ownership; a second worker must not be activated until stale-owner completion is prevented.

Deployment prerequisites: per-worker identity, token-fenced leases, safe retry/recovery, a verified shared PostgreSQL schema, 600-mode local credential file, and systemd units with per-node pacing. Do not copy credentials into GitHub. Keep Battlelog request pacing unchanged during concurrency validation.

Live baseline: 3,163 platoons, 71,883 pending soldier discoveries, 267 failed platoon requests, 74 failed discoveries. Excluded identities remain protected by the database trigger. Soldier admission errors do not invalidate an otherwise verified roster.
