"""Frozen Phase 3E endurance cohort for validation round three.

Generated from the successful read-only Phase 3E manifest freeze on 2026-10-04.
These BF4PS soldier IDs are the immutable execution boundary for the third
Phase 3E live endurance run. Earlier manifests remain preserved as historical
validation evidence.
"""

GLOBAL_ATTEMPT_CEILING = 120

PC_SOLDIER_IDS = (
    229, 230, 231, 232, 233, 234, 235, 236, 237, 238,
    239, 240, 241, 242, 243, 244, 245, 246, 247, 248,
    249, 250, 251, 252, 253, 254, 255, 256, 257, 258,
    259, 260, 261, 262, 263, 264, 265, 266, 267, 268,
)

PS4_SOLDIER_IDS = (
    888, 889, 890, 891, 892, 893, 894, 895, 896, 897,
    898, 899, 900, 901, 902, 903, 904, 905, 906, 907,
    908, 909, 910, 911, 912, 913, 914, 915, 916, 917,
    918, 919, 920, 921, 922, 923, 924, 925, 926, 927,
)

XBOXONE_SOLDIER_IDS = (
    987, 988, 989, 990, 991, 992, 993, 994, 995, 996,
    997, 998, 999, 1000, 1001, 1002, 1003, 1004, 1005, 1006,
    1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014, 1015, 1016,
    1017, 1018, 1019, 1020, 1021, 1022, 1023, 1024, 1025, 1026,
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
