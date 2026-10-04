"""Frozen Phase 3E endurance cohort.

Generated from the successful read-only Phase 3E manifest freeze on 2026-10-04.
These BF4PS soldier IDs are the immutable execution boundary for the first
Phase 3E live endurance run.
"""

GLOBAL_ATTEMPT_CEILING = 120

PC_SOLDIER_IDS = (
    36, 37, 38, 39, 40, 41, 42, 43, 44, 45,
    46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
    56, 57, 58, 59, 60, 61, 62, 63, 64, 65,
    66, 67, 68, 69, 70, 71, 72, 73, 74, 75,
)

PS4_SOLDIER_IDS = (
    124, 125, 126, 127, 128, 129, 130, 131, 132, 133,
    134, 135, 136, 137, 138, 139, 140, 141, 142, 143,
    144, 145, 146, 147, 148, 149, 150, 151, 152, 153,
    154, 155, 156, 157, 158, 159, 160, 161, 846, 847,
)

XBOXONE_SOLDIER_IDS = (
    169, 170, 171, 172, 173, 174, 175, 176, 177, 178,
    179, 180, 181, 182, 183, 184, 185, 186, 187, 188,
    189, 190, 191, 192, 193, 194, 195, 196, 197, 198,
    199, 200, 201, 202, 203, 204, 943, 944, 945, 946,
)

COHORT_BY_PLATFORM = {
    "pc": PC_SOLDIER_IDS,
    "ps4": PS4_SOLDIER_IDS,
    "xboxone": XBOXONE_SOLDIER_IDS,
}

COHORT_SOLDIER_IDS = PC_SOLDIER_IDS + PS4_SOLDIER_IDS + XBOXONE_SOLDIER_IDS

assert len(PC_SOLDIER_IDS) == 40
assert len(PS4_SOLDIER_IDS) == 40
assert len(XBOXONE_SOLDIER_IDS) == 40
assert len(COHORT_SOLDIER_IDS) == GLOBAL_ATTEMPT_CEILING
assert len(set(COHORT_SOLDIER_IDS)) == len(COHORT_SOLDIER_IDS)
