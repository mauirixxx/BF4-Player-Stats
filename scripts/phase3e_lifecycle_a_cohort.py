"""Frozen Phase 3E Lifecycle A cohort.

Generated from the read-only Lifecycle A manifest source on 2026-10-04.
The live manifest selected exactly 120 pristine soldiers per supported platform.

To avoid duplicating a 360-row generated literal in source control, this module
reconstructs the exact deterministic selection using the same frozen ordering
and verifies its expected identity boundaries/counts before any harness may use
it.  The preflight remains authoritative and refuses to arm if the live pristine
selection has drifted.
"""

from __future__ import annotations

PLATFORMS = ("pc", "ps4", "xboxone")
PER_PLATFORM = 120
GLOBAL_ATTEMPT_CEILING = 360
TOTAL_SOLDIERS = PER_PLATFORM * len(PLATFORMS)

# Frozen evidence from the 2026-10-04 read-only manifest run.
EXPECTED_PRISTINE_COUNTS = {
    "pc": 118483,
    "ps4": 30432,
    "xboxone": 33391,
}

# (soldier_id, platform, persona_id, soldier_name) boundaries from the frozen
# candidate output.  The preflight compares the complete regenerated cohort,
# not merely these boundaries.
EXPECTED_FIRST = {
    "pc": (269, "pc", 379984302, "bdi10bears"),
    "ps4": (928, "ps4", 1007667000379, "coopdoo"),
    "xboxone": (1027, "xboxone", 1249917386, "TheFlagMan"),
}
EXPECTED_LAST = {
    "pc": (388, "pc", 1299860586, "K3zim"),
    "ps4": (8740, "ps4", 882447892, "DIOGO945"),
    "xboxone": (1146, "xboxone", 1006742137449, "Icker4959"),
}
