"""Frozen three-soldier cohort for the Phase 3E survivor-progress closure."""

COHORT = (
    (390, 1328461452, "pc", "ObiJuanQueHuevos"),
    (391, 1399243002, "pc", "ASussyBaka"),
    (392, 1458587940, "pc", "Exospax"),
)
SOLDIER_IDS = tuple(row[0] for row in COHORT)
VICTIM_SOLDIER_ID = 390
SURVIVOR_SOLDIER_IDS = (391, 392)
