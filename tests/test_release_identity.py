from uuid import UUID
import pytest
from bf4ps.production_hosts import resolve_production_host


def test_explicit_identity_on_clean_node():
    env = {'BF4PS_COLLECTOR_UUID': '4c0cc22a-5b43-47a2-bdc9-7fb52e211345', 'BF4PS_COLLECTOR_NAME': 'fresh-01', 'BF4PS_EGRESS_KEY': 'site-a'}
    host, identity = resolve_production_host(environ=env, hostname='fresh-01.example.org')
    assert host == 'fresh-01'
    assert identity.collector_uuid == UUID(env['BF4PS_COLLECTOR_UUID'])
    assert identity.collector_name == 'fresh-01'
    assert identity.egress_key == 'site-a'


def test_unknown_host_refused():
    with pytest.raises(ValueError, match='New hosts require'):
        resolve_production_host(environ={}, hostname='fresh-01')


@pytest.mark.parametrize('env', [
    {'BF4PS_COLLECTOR_UUID': 'bad'},
    {'BF4PS_COLLECTOR_UUID': '4c0cc22a-5b43-47a2-bdc9-7fb52e211345', 'BF4PS_COLLECTOR_NAME': 'fresh-01'},
    {'BF4PS_COLLECTOR_UUID': '00000000-0000-0000-0000-000000000000', 'BF4PS_COLLECTOR_NAME': 'fresh-01', 'BF4PS_EGRESS_KEY': 'site-a'},
])
def test_partial_or_invalid_identity_refused(env):
    with pytest.raises(ValueError):
        resolve_production_host(environ=env, hostname='fresh-01')


def test_legacy_host_kept_for_soak_compatibility():
    host, identity = resolve_production_host(environ={}, hostname='tcou')
    assert host == 'tcou'
    assert identity.collector_name == 'phase3e-tcou'
