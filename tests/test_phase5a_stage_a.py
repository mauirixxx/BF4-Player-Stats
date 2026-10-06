from pathlib import Path

def test_phase5a_stage_a_common_locks_experiment_boundaries():
    source = Path("scripts/phase5a_stage_a_common.py").read_text(encoding="utf-8")
    assert "GLOBAL_ATTEMPT_CEILING = 30" in source
    assert "REQUEST_INTERVAL_SECONDS = 5.0" in source
    assert "RETRY_AFTER_SECONDS = 86400" in source
    assert '"hnl-01"' in source and '"kah-01"' in source and '"tcou"' in source
    assert "FROZEN_COHORT" in source

def test_phase5a_stage_a_worker_is_weapons_only_and_bounded():
    source = Path("scripts/phase5a_stage_a_worker.py").read_text(encoding="utf-8")
    assert "collect_one_weapon_job" in source
    assert "collect_one_detailed_job" not in source
    assert "collect_one_vehicle" not in source
    assert "allowed_soldier_ids=SOLDIER_IDS" in source
    assert "max_total_attempts=GLOBAL_ATTEMPT_CEILING" in source
    assert "retry_after_seconds=RETRY_AFTER_SECONDS" in source
    assert "http_status in {403, 429}" in source

def test_phase5a_stage_a_seed_only_creates_weapon_jobs():
    source = Path("scripts/phase5a_stage_a_seed.py").read_text(encoding="utf-8")
    assert 'resource="weapons"' in source
    assert "FROZEN_COHORT" in source
    assert "enqueue_job" in source
    assert 'resource="vehicles"' not in source

def test_phase5a_stage_a_audit_is_read_only():
    source = Path("scripts/phase5a_stage_a_audit.py").read_text(encoding="utf-8")
    assert "engine.connect()" in source
    assert "engine.begin()" not in source
    upper = source.upper()
    assert "INSERT INTO" not in upper
    assert "UPDATE COLLECTION" not in upper
    assert "DELETE FROM" not in upper


def test_phase5a_stage_a_worker_does_not_invent_database_hostname_contract():
    common = Path("scripts/phase5a_stage_a_common.py").read_text(encoding="utf-8")
    worker = Path("scripts/phase5a_stage_a_worker.py").read_text(encoding="utf-8")
    assert "EXPECTED_DB_HOST" not in common
    assert "EXPECTED_DB_HOST" not in worker
    assert "parsed.hostname" not in worker
    assert 'parsed.path.lstrip("/") != EXPECTED_DATABASE' in worker
    assert "assert_target(conn)" in worker


def test_phase5a_stage_a_records_physical_attempt_before_http():
    collector = Path("bf4ps/weapon_collector.py").read_text(encoding="utf-8")
    assert "collection_attempt_started" in collector
    assert collector.index("_record_attempt_started(") < collector.index("fetch_weapon_stats(")


def test_phase5a_stage_a_bounded_claim_counts_durable_attempt_starts():
    jobs = Path("bf4ps/collection_jobs.py").read_text(encoding="utf-8")
    assert "collection_attempt_started" in jobs
    assert "GROUP BY job_id, attempt_number" in jobs
    assert "d.attempt_number = j.attempt_count" in jobs


def test_phase5a_stage_a_audit_reconciles_physical_and_terminal_attempts():
    audit = Path("scripts/phase5a_stage_a_audit.py").read_text(encoding="utf-8")
    assert "exactly 30 durable physical weapon attempts exist" in audit
    assert "every physical attempt has exactly one durable terminal outcome" in audit
    assert "all three frozen collectors participated in physical attempts" in audit


def test_phase5a_stage_a_audit_reports_all_failures_before_exit():
    audit = Path("scripts/phase5a_stage_a_audit.py").read_text(encoding="utf-8")
    assert "failures_found.append" in audit
    assert "FAIL ({len(failures_found)} check(s))" in audit
    assert "return 1" in audit
    assert "raise AssertionError" not in audit


def test_weapon_collector_preserves_post_request_persistence_failures():
    collector = Path("bf4ps/weapon_collector.py").read_text(encoding="utf-8")
    assert "collection_persistence_failure" in collector
    assert "'persistence_failure'" in collector
    assert "'stage', 'persist_weapon_success'" in collector
    assert "_record_persistence_failure(" in collector
    assert "raise" in collector


def test_stage_a_audit_rejects_persistence_layer_failures():
    audit = Path("scripts/phase5a_stage_a_audit.py").read_text(encoding="utf-8")
    assert "event_type='collection_persistence_failure'" in audit
    assert "no persistence-layer failure evidence" in audit
    assert "===== PERSISTENCE FAILURES =====" in audit
