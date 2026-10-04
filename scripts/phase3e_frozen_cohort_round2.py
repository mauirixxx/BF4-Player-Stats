"""Frozen Phase 3E endurance cohort for validation round two.

Generated from the successful read-only Phase 3E manifest freeze on 2026-10-04.
These BF4PS soldier IDs are the immutable execution boundary for the second
Phase 3E live endurance run. The first-run manifest remains preserved in
phase3e_frozen_cohort.py as historical validation evidence.
"""

GLOBAL_ATTEMPT_CEILING = 120

PC_SOLDIER_IDS = (
    76, 77, 78, 79, 80, 81, 82, 83, 84, 85,
    86, 87, 88, 89, 90, 91, 92, 205, 206, 207,
    208, 209, 210, 211, 212, 213, 214, 215, 216, 217,
    218, 219, 220, 222, 223, 224, 225, 226, 227, 228,
)

PS4_SOLDIER_IDS = (
    848, 849, 850, 851, 852, 853, 854, 855, 856, 857,
    858, 859, 860, 861, 862, 863, 864, 865, 866, 867,
    868, 869, 870, 871, 872, 873, 874, 875, 876, 877,
    878, 879, 880, 881, 882, 883, 884, 885, 886, 887,
)

XBOXONE_SOLDIER_IDS = (
    947, 948, 949, 950, 951, 952, 953, 954, 955, 956,
    957, 958, 959, 960, 961, 962, 963, 964, 965, 966,
    967, 968, 969, 970, 971, 972, 973, 974, 975, 976,
    977, 978, 979, 980, 981, 982, 983, 984, 985, 986,
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
