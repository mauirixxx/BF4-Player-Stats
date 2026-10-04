"""Exact frozen Phase 3E Lifecycle A cohort captured on 2026-10-04."""
from __future__ import annotations
PLATFORMS=("pc","ps4","xboxone")
PER_PLATFORM=120
GLOBAL_ATTEMPT_CEILING=360
TOTAL_SOLDIERS=360
COHORT_BY_PLATFORM={
 "pc":tuple(range(269,389)),
 "ps4":tuple(range(928,943))+tuple(range(8635,8680))+tuple(range(8681,8741)),
 "xboxone":tuple(range(1027,1147)),
}
COHORT_SOLDIER_IDS=tuple(s for p in PLATFORMS for s in COHORT_BY_PLATFORM[p])
assert all(len(COHORT_BY_PLATFORM[p])==PER_PLATFORM for p in PLATFORMS)
assert len(COHORT_SOLDIER_IDS)==TOTAL_SOLDIERS and len(set(COHORT_SOLDIER_IDS))==TOTAL_SOLDIERS
EXPECTED_FIRST={"pc":269,"ps4":928,"xboxone":1027}
EXPECTED_LAST={"pc":388,"ps4":8740,"xboxone":1146}
