"""Read-only live BF4PS fleet telemetry aggregator."""
from concurrent.futures import ThreadPoolExecutor
import json
import time
from urllib.request import urlopen

HOSTS = {
    'mak-01': ('192.168.10.70', 'stats', 'ranking shard 0/4'),
    'mak-02': ('192.168.10.75', 'stats', 'ranking shard 1/4'),
    'mak-03': ('192.168.10.73', 'stats', 'ranking shard 2/4'),
    'mak-04': ('192.168.10.74', 'stats', 'ranking shard 3/4'),
    'mak-05': ('192.168.10.79', 'platoon', ''),
    'mak-06': ('192.168.10.76', 'stats', ''),
    'hnl-01': ('192.168.5.70', 'stats', ''),
    'hnl-02': ('192.168.5.69', 'stats', ''),
    'hnl-03': ('192.168.5.68', 'stats+platoon', ''),
    'kah-01': ('192.168.21.70', 'stats', ''),
    'rnt-01': ('192.168.200.47', 'stats', ''),
}
PLATOON = ('bf4ps-platoon-alternating.service', 'bf4ps-platoon-queue.service')

def _get(item):
    host, (ip, role, extra) = item
    try:
        with urlopen('http://' + ip + ':8772/status', timeout=1.8) as resp:
            data = json.load(resp)
        if data.get('host', '').lower() != host:
            raise ValueError('Telemetry host mismatch')
        if abs(time.time() - data.get('at', 0)) > 30:
            raise ValueError('Stale telemetry')
        return host, data, None
    except Exception as exc:
        return host, None, type(exc).__name__

def fleet_rows():
    nodes = []
    with ThreadPoolExecutor(max_workers=len(HOSTS)) as pool:
        observations = dict((host, (data, err)) for host, data, err in pool.map(_get, HOSTS.items()))
    for host, (ip, role, extra) in HOSTS.items():
        data, err = observations[host]
        if data is None:
            nodes.append(dict(name=host, host=host, role=role + (' + ' + extra if extra else ''),
                              status='unknown', detail='Telemetry unreachable (' + err + ')'))
            continue
        containers = data.get('containers', {})
        services = data.get('services', {})
        stats_state = containers.get('bf4ps-production-collector')
        platoon_states = {unit: services.get(unit, {}).get('ActiveState', 'unknown') for unit in PLATOON}
        if 'stats' in role:
            nodes.append(dict(name=host + ' stats', host=host,
                              role='Player stats collection' + (' + ' + extra if extra else ''),
                              status='healthy' if stats_state == 'running' else 'stopped' if stats_state else 'unknown',
                              detail='Docker collector: ' + str(stats_state or 'not found')))
        if 'platoon' in role:
            # The alternating worker can run as a timer-triggered oneshot.
            # Report observed process state, not presumed collection success.
            timer = services.get('bf4ps-platoon-alternating.timer', {}).get('ActiveState', 'unknown')
            running = any(x in ('active', 'activating') for x in platoon_states.values())
            state = 'healthy' if running else 'stale' if timer == 'active' else 'stopped'
            nodes.append(dict(name=host + ' platoons', host=host, role='Platoon roster collection',
                              status=state, detail='Alternating: ' + platoon_states[PLATOON[0]] +
                              ' · Queue: ' + platoon_states[PLATOON[1]] + ' · Timer: ' + timer))
        if extra:
            rank = services.get('bf4ps-compact-ranking.service', {}).get('ActiveState', 'unknown')
            nodes.append(dict(name=host + ' ranking', host=host, role=extra,
                              status='healthy' if rank == 'active' else 'stopped' if rank != 'unknown' else 'unknown',
                              detail='Publisher: ' + rank))
        if host in ('mak-01', 'rnt-01'):
            name = 'bf4ps-discord-ha-' + ('mak' if host == 'mak-01' else 'rnt')
            state = containers.get(name)
            nodes.append(dict(name=name, host=host, role='Discord HA bot', status='healthy' if state == 'running' else 'stopped' if state else 'unknown', detail='Docker: ' + str(state or 'unknown') + ' · Image: ' + data.get('images', {}).get(name, 'unknown') + ' · HA leadership not measured'))
        if host == 'mak-01':
            for unit in ('bf4ps-watchdog.timer', 'bf4ps-watchdog.service'):
                svc = services.get(unit, {})
                state = svc.get('ActiveState', 'unknown')
                ok = state in ('active', 'activating') or (unit.endswith('.service') and state == 'inactive' and svc.get('Result') == 'success')
                nodes.append(dict(name=unit, host=host, role='Discord alert watchdog', status='healthy' if ok else 'unknown' if state == 'unknown' else 'stopped', detail=state + ' · ' + svc.get('UnitFileState', 'unknown') + ' · ' + svc.get('Result', 'unknown')))
        for unit in ('bf4ps-weapon-metrics-sync.service', 'bf4ps-vehicle-metrics-sync.service'):
            svc = services.get(unit)
            if svc and svc.get('ActiveState') == 'failed':
                nodes.append(dict(name=unit, host=host, role='Equipment metrics reconciliation',
                                  status='stopped', detail='systemd failed: ' + svc.get('Result', 'unknown')))
    return nodes, {'stats_nodes': 10, 'platoon_nodes': 2, 'ranking_nodes': 4,
                   'responding': sum(data is not None for data, err in observations.values()),
                   'total': len(HOSTS)}
