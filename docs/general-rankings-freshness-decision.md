# General leaderboard snapshot freshness decision (scratch investigation)

Status: periodic as-of snapshot semantics approved 2026-11-15; scratch reader updated and tested; no production activation or schema change.

## Verified behavior

- The publisher ranks successful, nonexcluded detailed-stat soldiers into an immutable generation and atomically updates the published pointer.
- The existing website reader recomputes current statistics on every request; its semantics are different from a periodically refreshed snapshot.
- On the 560,000-soldier RNT-01 fixture, the approved as-of reader immediately hides an excluded member while retaining historical position, rank, and population. The visible filtered count decreases. The exclusion test was rolled back.
- Newly eligible soldiers and changes to existing soldiers' kills do not change published positions until the next generation. Both tests passed and were rolled back.
- The experimental reader is not wired into the website. A None result indicates no published generation; website integration and fallback remain outstanding.

## Recommended contract

1. **Snapshot semantics**: display ranks and percentiles as of the generation publication, not as live instantaneous ranks. Surface publication time and refresh age in the website. Newly collected or updated players appear after the next publication. Do not claim live parity between publications.
2. **Moderation safety**: never display an actively excluded player. Filter exclusions and deleted identities at read time, retaining original as-of positions, ranks, divisions and cohort population without renumbering. The filtered count reflects currently visible snapshot members. Label the website clearly as an as-of snapshot.
3. **Atomicity**: ensure all statements of a request use the same committed generation and consistent PostgreSQL read snapshot; a plain READ COMMITTED transaction does not provide a single snapshot across multiple statements. Use a suitable read-only REPEATABLE READ transaction, or an equivalent single-statement design. Retention must not delete a generation while readers are using it.
4. **Refresh scheduling**: keep publisher independent of equipment compact ranking. Measure full-scope cycle duration, WAL, disk and replica impact before enabling any production scheduler. Do not invalidate a snapshot on every detailed collector update: doing so would defeat periodic precomputation.
5. **Testing**: cover generation replacement and retention races, exclusions, deletion, new eligibility, source stat updates, ties, empty scopes, search aliases, and page boundaries.

## Unresolved before production

- Product decision resolved: periodic as-of rankings, not strict live-ranking semantics.
- Generation freshness age target and retention policy.
- Reader transaction boundary and website fallback wiring.
- Name-search query optimization, production-like load tests and deployment gates.
