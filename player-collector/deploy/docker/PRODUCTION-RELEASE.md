# Production collector release and verification

GitHub `main` is the source of truth. Do not copy Python modules into a running container or treat `docker commit` as a durable release. Every production collector image must be built from an exact reviewed Git SHA and all nodes must run that exact release. Preserve per-node identity, egress key, database URL, network mode, and restart policy. Do not run database migrations as part of collector deployment.

## Build and smoke-test

```sh
git fetch origin
git checkout --detach <reviewed-full-SHA>
cd player-collector
docker build --label org.opencontainers.image.revision=<reviewed-full-SHA> -t bf4-player-stats:git-<short-SHA> .
docker run --rm --entrypoint python bf4-player-stats:git-<short-SHA> -c 'import inspect; import bf4ps.collection_jobs as j; import bf4ps.production_hosts as p; assert p.REQUEST_INTERVAL_SECONDS == 4.0; assert "excluded.active" in inspect.getsource(j.claim_next_job)'
```

Builds from different hosts can have different image IDs when their base images or unpinned Python dependencies differ; matching tags alone do not establish identical binaries. Prefer publishing one digest-pinned image to a trusted registry or transporting a single validated image archive. Verify the digest and running container image ID after restart.

## Rollout safety

1. Record existing container ID/image, command, environment variable *names* (never publish secret values), network mode, restart policy, and recent successes. Preserve the original container for rollback.
2. Check the live database Alembic revision and physical dispatch ceilings without modifying either.
3. Deploy one canary with the exact same runtime identity, environment, and network configuration. Do not run two collectors with the same identity concurrently.
4. Verify fresh successful resource collections, excluded-job skip behavior, and absence of 403/429 or rising connection errors.
5. Roll out one host at a time, preserving Compose ownership on `rnt-01`, then verify all nine collectors by **direct import from the running container** and by recent successful logs.
6. Monitor BF4PS and BF4SW separately for IP blocking and sustained throughput degradation. The 4-second interval does not override the shared 4,800/hour physical dispatch budget.
7. Keep rollback images/containers until sustained soak passes. Revert the release if collectors fail startup or the Battlelog error rate increases.

Do not mistake a source checkout, an image built but not started, or a host-local `docker commit` tag for a verified deployed release.
