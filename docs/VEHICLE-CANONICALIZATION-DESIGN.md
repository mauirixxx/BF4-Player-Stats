# Vehicle leaderboard canonicalization (D3 audit, 2026-10-13)

Scope: read-only website leaderboard; never alter collected stats or source catalog IDs. D3 is the only allowed API database.

## Rules

For each soldier, first deduplicate rows for the same raw vehicle ID using MAX(kills). Then normalize by family:

- SUM distinct variants: DV15 IDs 2+30 (canonical 2), Z11 IDs 41+63 (canonical 41).
- MAX overlapping or mirrored variants: M1 ABRAMS 47+67 (47); T90 27+5 (27); LAV25 46+56 (46); BTR90 78+68 (78); UH1Y 4+36+23 (4); HIMARS 1+73 (1); SPM3 17+15 (17); KA60 52+13 (52); BOMBER 16+76+34 (16); .50 CAL 8+21 (8); UCAV 10+54 (10).
- Zero-only placeholders: AH6 62 alongside 80, LAVAD 26 alongside 32, 9K22 71 alongside 44, Z11 55 alongside 41+63. Suppress a zero-only placeholder only while its total is zero; if future collection makes it nonzero, expose it separately for investigation rather than silently discarding kills.
- All platform filtering and success-state filtering precede aggregation.
- The item leaderboard and catalog totals must use identical normalization. Population remains distinct soldiers with successfully collected rows for the family. Do not invent missing soldiers or sum mirrored records.
- Legacy item IDs should resolve to their canonical family, except zero-only placeholder IDs when they gain nonzero kills.
- Keep cross-catalog weapon zero visibility behavior unchanged.

## Validation gates

Verify documented tables/columns against live D3 before SQL changes. Test all/pc/ps4/xboxone, raw versus canonical IDs, 2,237-soldier totals, expected MAX and SUM examples, zero-only behavior, rank/population consistency, and API health. Do not deploy without passing live read-only staging checks.
