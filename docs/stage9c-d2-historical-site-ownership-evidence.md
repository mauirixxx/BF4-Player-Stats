# Stage 9C D2 three-site ownership evidence

Read-only forensic checkpoint for failed run `bf4ps-d2-three-hour-soak-20261011-v1`. No historical records were changed.

## Observed outcomes

Per-round durable collection-success counts (site order tcou / kah-01 / hnl-01):

| Round | tcou | kah-01 | hnl-01 |
|---|---:|---:|---:|
| 1 | 3 | 3 | 3 |
| 2 | 0 | 5 | 4 |
| 3 | 0 | 4 | 5 |
| 4 | 0 | 0 | 9 |
| 5 | 0 | 0 | 9 |
| 6, incomplete | 0 | 0 | 6 |
| Total | 3 | 12 | 36 |

The immutable `soak_round_jobs` mapping was used to attribute successful events to soldiers. Joining historical success events to `collection_jobs` alone returns no completed jobs because successful queue entries have been deleted; use the soak attribution ledger instead.

All nine soldiers (IDs 565 through 573) have success events attributed to `hnl-01`. All nine also have success events attributed to `kah-01`. `tcou` recorded successes for 565, 566 and 571. This demonstrates that the historical run did **not** enforce exclusive three-soldier site ownership.

## Recovery implementation and next gate

The current recovery worker limits allowed_soldier_ids to the three personas assigned to its hostname; the current HTTP admission callback independently verifies persona-to-site ownership inside the start transaction. Offline regression coverage exists for disjoint partitions, restricted selection and foreign-site rejection. These changes are subsequent to the historical run; historical behavior must not be treated as evidence of a new-run result.

Before authorizing a fresh live soak: inspect collector queue claim and fairness behavior under site restrictions, add offline multi-round tests ensuring each of three sites receives only its three soldiers per round, and confirm that terminal reporting detects any cross-site event attribution. Retain the historical run unchanged. Production remains HOLD.
