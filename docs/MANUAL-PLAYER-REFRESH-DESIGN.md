# Manual player refresh and Battlelog URL intake — implementation contract
Status: DESIGN APPROVED IN PRINCIPLE; backend NOT implemented
Recorded: 2026-10-14 (Hawaii local)
Scope: BF4 Player Stats public website, production PostgreSQL coordination, distributed collectors.

## User-facing requirements
1. Soldier dossier shows boxed Battlelog link for PC, PS4, and Xbox One; it is the FIRST action.
2. BF4DB, Battlefield Agency, and BF4 Cheat Report links appear ONLY for PC soldiers. Derive URLs from persona_id:
   - https://bf4db.com/player/{persona_id}
   - https://battlefield.agency/player/by-persona_id/bf4/{persona_id}
   - https://bf4cheatreport.com/?pid={persona_id}&uid=&cnt=200
   - Battlelog: https://battlelog.battlefield.com/bf4/soldier/{encoded_current_name}/stats/{persona_id}/{platform}/
3. Refresh Stats button exists as a DISABLED placeholder until backend is operational. Never pretend that clicking a placeholder submits work.
4. Once operational, manual refresh may request priority collection only when the relevant gameplay statistics have not been successfully collected in the preceding 60 minutes. Cooldown also applies to repeated manual requests, including while a request is queued or running.
5. Offer a separate input accepting a Battlelog BF4 soldier stats URL. Validate URL, platform and persona_id; identify soldier by (platform, persona_id), NOT display name. Existing soldier => priority request; missing soldier => safely register and request initial collection.
6. Show queued/running/success/failure states and real timestamps. Priority is NOT a guarantee of immediate completion.

## Timestamp semantics (do not conflate)
Existing collection_state timestamps exposed to website:
- detailed_last_success_at
- weapons_last_success_at
- vehicles_last_success_at
- profile_last_success_at
These represent successful persisted collection, NOT button clicks.
Record manual_refresh_requested_at (or equivalent separate durable request record) at accepted submission. NEVER alter last_success_at on click.
Eligibility should be evaluated server-side transactionally, against last successful collection and last manual request, using a 60-minute window. Gameplay resource freshness should be evaluated independently; profile-only success must not suppress stale gameplay stats. Define whether button represents full refresh and how partially fresh resources are handled before coding.

## Architecture and security
- Public read-only website account must retain read-only access to stats tables.
- A narrowly privileged authenticated service/role or SECURITY DEFINER function may enqueue only validated priority requests; no generic public table write credentials or direct collector stats writes.
- Reuse existing dispatcher, claims, lease, idempotency, retry/backoff, and per-egress request pacing; priority changes admission ORDER, not external request RATE.
- Deduplicate outstanding requests for same (platform, persona_id, resource). Ensure fairness: normal scheduled jobs must continue.
- Abuse controls: per-player 60-minute cooldown, request validation, bounded pending queue, global/IP-level rate limiting, and clear feedback. Avoid leaking sensitive internals.
- Keep BF4 Server Watcher DB separate; BF4PS collectors require no write access to BF4SW.

## Implementation sequence — avoid unrelated testing rabbit holes
1. Inspect authoritative BF4PS schema and verify against live PostgreSQL. Inspect existing scheduler/admission/collection-state implementation; document exact tables and constraints.
2. Finalize concise queue schema/API contract and security grants. Confirm expected behavior for failed and partially completed refreshes.
3. Implement queue and atomic 60-minute eligibility/deduplication, plus worker priority claim while preserving per-egress pacing and fairness.
4. Add safe Battlelog URL intake with canonical (platform, persona_id) identity and idempotent soldier insertion.
5. Wire button and input; show pending/running/updated/error states. Preserve accurate last_success_at semantics.
6. Run focused tests (simultaneous clicks, cooldown, missing soldier, malformed URL, failed collection, multiple workers, ordinary-job fairness), then bounded live smoke test.
7. Deploy, verify public read-only role remains read-only, commit/push and document observed results.

## Out of scope for first release
- Changes to BF4SW schema or collectors.
- Broad collector pacing redesign or multiweek soak.
- User authentication/social features unless required for basic abuse prevention.
- Full statistics collection triggered directly from the web request handler.

## Existing frontend implementation
site/soldier.html: boxed platform-appropriate external links and disabled Refresh Stats placeholder.
