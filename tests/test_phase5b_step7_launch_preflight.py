from bf4ps.phase5b_step7_endurance import HOSTS
import ast
from pathlib import Path
P=Path("scripts/phase5b_step7_launch_preflight.py")
def test_launch_preflight_parses_and_is_read_only():
 s=P.read_text(); ast.parse(s,filename=str(P))
 assert "engine.connect()" in s and "engine.begin()" not in s
 assert "INSERT " not in s and "UPDATE " not in s and "DELETE " not in s
 assert "Battlelog requests: 0" in s
def test_launch_preflight_requires_pristine_seed_and_collectors():
 s=P.read_text()
 for x in ("INITIAL_JOB_COUNT","attempt_count=0","collection_attempt_started",
  "foreign_background_jobs=0","current_job_id","enabled","drained","FROZEN_UUIDS"):
  assert x in s


def test_frozen_host_identity_shape_matches_preflight_access():
    assert set(HOSTS)=={"hnl-01","kah-01","tcou"}
    for hostname, host in HOSTS.items():
        assert hostname
        assert host.collector_uuid
        assert host.collector_name
        assert host.egress_key
        assert not hasattr(host, "hostname")
