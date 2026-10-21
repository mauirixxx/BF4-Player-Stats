# BF4PS D3 — bounded real-data ramp checkpoint (2026-10-11)

Status: **COHORT CANDIDATES / PREFLIGHT ONLY; NO LIVE HTTP AUTHORIZED BY THIS DOCUMENT**. Production BF4SW and historical D2 remain untouched.

## Baseline and evidence
D3 three-site synthetic 600-second run passed: tcou 162174 cycles, kah-01 3917, hnl-01 4496; all 900 synthetic jobs returned to pending; zero ownership errors. This does not validate real HTTP or stat persistence. Earlier real Battlelog D2 and integration runs established detailed, weapons, vehicles and cross-platform normalization/persistence. Historical Phase 4B 900-PC and Phase 4C 450-multiplatform detailed cohorts also passed after expected transient normalization failures/retries.

## First nine known, previously successful PC candidate identities
Source: docs/bf4ps-first-three-site-live-ignition-2026-10-11.md. These are candidate names, not newly validated D3 DB rows. Preserve exact persona IDs from the original run manifest or validated database; **do not resolve by name alone or invent IDs**.

- tcou: It_Mip, malilahygge, JonNZzin
- kah-01: GORBON_TREEMAN, stelyo_berberaks, pirulaconcaca
- hnl-01: yukonsunshine, FrankoPop, MLGPILLO

The nine were successfully collected for detailed, weapons and vehicles in the prior D2 live tests; rerunning them is a refresh, not first-ever collection.

## Proposed larger candidate selection
Target 300 distinct (platform, persona_id) identities: 100 per physical site; balanced 100 PC, 100 PS4, 100 Xbox One overall, preferably a deterministic stratification of the validated source census. Produce a frozen immutable manifest with soldier name, platform, persona ID, source DB, assignment, and checksum. Use read-only selection from an authorized existing real-soldier database. D3 currently contains synthetic PC soldiers, **not a 300-player real multiplatform cohort**. Do not repurpose D3 without separate schema/identity preflight and an isolated real-data target plan.

## Rate and safety
- Three confirmed separate public egress IPs; at least 5 seconds between physical Battlelog HTTP starts per egress.
- Absolute global rolling-hour ceiling 1296 physical dispatches; budget accounts for failures and ambiguous starts, not merely successful jobs.
- Full refresh of 300 soldiers = 900 planned physical requests (detailed, weapons, vehicles). Never assume three resources are atomic; reconcile each independently.
- First 30 soldiers/90 requests, then 90 more/270 requests, then 180 more/540 requests, with hard stop after each stage and read-only reconciliation.
- Freeze a unique run ID, UTC window, exact cohort manifest, immutable event baseline, per-site and global attempt ceilings, and crash-safe durable job/run attribution before execution.
- Stop on HTTP 403/429, budget/egress-gate violation, identity drift, lost lease, unaccounted request, or unexpected queue contamination. No automatic retry storm; all physical attempts consume budget.
- Maintain BF4SW production HOLD and avoid modifying historical D2 or synthetic D3 evidence.

## Next implementation gate
1. Verify current documented schema against migration head and live target; reconcile stale schema-reference head before any persistence changes.
2. Read-only select 300 exact persona/platform identities and confirm eligibility, existing collection states, and no foreign jobs; freeze manifest in repo.
3. Audit the live worker's physical dispatch ledger and restart-safe round/job attribution; correct any gaps in a dedicated branch with tests.
4. Run preflight on all three physical sites, inspect shared public egress load with BF4SW, then request explicit ignition after objective PASS.
