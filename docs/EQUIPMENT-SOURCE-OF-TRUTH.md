# BF4 equipment naming and leaderboard rules — implementation handoff

**Read this before editing equipment names, catalog selectors, or leaderboard aggregation.** Recovered from the October 13–14, 2026 audit in *Plan Player Stats Project part 5*. These files were previously isolated on the `docs/equipment-display-name-audit` Git branch; copied to the active website branch on October 14 so the decisions are discoverable where the website is developed.

## Authority and scope

1. **Authoritative audited name inventory:** [`catalog/equipment-name-inventory.csv`](catalog/equipment-name-inventory.csv), keyed by `(kind, catalog_id)` with original `raw_key`, `proposed_label`, `status`, and `source`. The 233-row audit covers 170 visible weapons and 63 visible vehicles at its D3 snapshot, **not** every raw catalog entry. The live API may expose different counts; don't mistake that for an audit error or assume all current raw IDs have been reviewed.
2. **Evidence and review decisions:** [`EQUIPMENT-DISPLAY-NAME-AUDIT.md`](EQUIPMENT-DISPLAY-NAME-AUDIT.md). Some early sections document superseded uncertainty; read later closure sections before changing a label.
3. **Vehicle aggregation:** [`VEHICLE-CANONICALIZATION-DESIGN.md`](VEHICLE-CANONICALIZATION-DESIGN.md), implemented in `api/leaderboard_api.py`. Canonicalization is **not** merely deduplicating equal display strings.
4. **Website display implementation:** `site/index.html` contains `equipmentLabels`; `site/equipment.html` currently copies that map. These are **generated/consumer representations**, not independent naming authorities. Future updates should reconcile them against the CSV and preserve the CSV's confidence/status distinctions. Avoid adding yet another divergent dictionary.

## Verified decisions that must not be regressed

- MKV maps to **XD-1 ACCIPITER**; independently verified against Battlelog counts for mauirixxx and Suzems (commit `91847d3`).
- UCAV remains **UCAV**, without faction-specific naming or aggregation changes (commit `3c59633`).
- COUGAR maps to **MRAP**, independently checked against two Battlelog profiles (commit `c662cb7`).
- All eight numbered Battlepack knives were verified by operator/player Battlelog comparisons: BPKNIFE1 IMPROVISED; 2 SCOUT; 3 TRENCH; 4 CARBON FIBER; 5 SURVIVAL; 6 BOWIE; 7 BOOT; 8 SEAL (commit `4805393`).
- USAS12NV display is **USAS-12 FLIR**, not NV (commit `93aee14`).
- The redundant **.50 CAL (NO SHIELD)** entry is hidden from the vehicle picker (commit `fe30961`). Do not hide the canonical .50 CAL family.
- Duplicate/overlapping vehicle families are resolved by **per-soldier MAX for mirrors**, **SUM for independently additive variants**, and explicitly audited zero-only placeholder suppression; see canonicalization design. Never blindly SUM all same-name vehicle IDs or remove raw database rows.
- Cross-catalog zero-kill weapons with active vehicle counterparts are hidden from weapon selection (commit `7f16d92`). This is a display/catalog policy, not deletion of stats.

## Rules for future changes

- Consult the CSV and the audit report **before** editing labels; don't infer exact names from localization suffixes, a wiki alone, or a previous assistant summary.
- Consult the canonicalization design **and current API code** before modifying deduplication, ranking, or catalog visibility. Verify documented database schema against live PostgreSQL before SQL changes.
- Preserve `(kind, catalog_id)` and `raw_key`; display labels are presentation metadata, not identity keys.
- A Battlelog-confirmed label is not equivalent to a candidate; keep the recorded confidence status and evidence. Changes to display labels must not change raw stats, historical records, or collector behavior.
- Update CSV and Markdown evidence together for a new audit decision. Update website consumers in a separate verified change. Test PC, PS4, Xbox One, all-platform rankings, catalog counts, canonical legacy IDs, and representative overlapping/zero-only cases before deploying API changes.

## Historical implementation trail

`6c44762` established the CSV authority; `4d85d95` implemented canonical vehicle leaderboard aggregation; `7f16d92` handled cross-catalog zero-only weapons; `fe30961` hid the redundant unshielded .50 CAL; `0798aca` merged approved website names. The current separate equipment page (`site/equipment.html`) was created later and must be kept consistent with these decisions.
