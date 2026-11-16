"""Offline tests for opt-in as-of general rank reader."""
from pathlib import Path
import ast
import pytest

READER = Path(__file__).resolve().parents[1] / 'bf4ps' / 'general_rank_reader.py'
SOURCE = READER.read_text()
TREE = ast.parse(SOURCE)

def test_snapshot_semantics():
    assert 'published_at' in SOURCE
    assert 'generation_id' in SOURCE
    assert 'r.position LIMIT :limit OFFSET :offset' in SOURCE
    assert 'NOT EXISTS (SELECT 1 FROM player_exclusions' in SOURCE
    assert 'r.rank*100.0/NULLIF(:population,0)' in SOURCE
    assert 'SELECT count(*) FROM general_rank_rows' in SOURCE
    assert 'eligible) != population' not in SOURCE

def test_no_schema_writes_or_unsafe_query_interpolation():
    assert not any(word in SOURCE for word in ('INSERT INTO', 'DELETE FROM', 'UPDATE general_rank'))
    assert 'if metric not in METRICS or platform not in PLATFORMS' in SOURCE
    assert "if search:" in SOURCE
    assert "if division:" in SOURCE
    assert 'r.generation_id=:generation_id' in SOURCE

def test_exclusion_and_alias_filters():
    assert 'pe.active' in SOURCE
    assert 'JOIN soldiers s ON s.soldier_id=r.soldier_id' in SOURCE
    assert 'SELECT soldier_id FROM soldier_names WHERE lower(name) LIKE :pattern' in SOURCE
    assert 'SELECT soldier_id FROM soldiers WHERE lower(current_name) LIKE :pattern' in SOURCE
    assert 'SELECT soldier_id FROM soldiers WHERE persona_id::text LIKE :pattern' in SOURCE

def test_reader_uses_published_generation():
    assert 'general_rank_published p' in SOURCE
    assert 'g.completed_at IS NOT NULL' in SOURCE
    assert "if published is None:" in SOURCE
