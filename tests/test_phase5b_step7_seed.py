import ast
from pathlib import Path
SEED=Path("scripts/phase5b_step7_seed.py")
AUDIT=Path("scripts/phase5b_step7_seed_audit.py")
def test_seed_freezes_cohort_in_marker_and_exact_queue():
 s=SEED.read_text()
 assert "pg_advisory_xact_lock" in s
 assert "cohort_soldier_ids" in s
 assert "FOR UPDATE OF s,cs" in s
 assert "inserted!=INITIAL_JOB_COUNT" in s
 assert "Battlelog requests: 0" in s
def test_seed_audit_is_read_only_and_checks_zero_attempts():
 s=AUDIT.read_text()
 assert "engine.connect()" in s and "engine.begin()" not in s
 assert "INSERT " not in s and "UPDATE " not in s and "DELETE " not in s
 assert "collection_attempt_started" in s
 assert "foreign background jobs exist" in s
 assert "Battlelog requests: 0" in s


def test_step7_seed_and_audit_are_python_syntax_valid():
    for path in (SEED, AUDIT):
        ast.parse(path.read_text(), filename=str(path))
