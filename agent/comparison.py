"""Recorded-configuration eligibility for algorithm comparisons (no model/I/O)."""
import math

RUNNERS = {'netem_nines.py', 'netem_cubic_benchmark_nines.py', 'netem_cubic_benchmark_hotnets.py'}
METADATA = {'notes', 'tags', 'experiment_name', 'client_ccas'}


def numeric(value):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def recorded_configuration(parent, runs, job):
    """Keep all recorded non-CCA launch settings, plus actual client/link settings."""
    clients = [{
        'client_number': numeric(r.get('client_number')),
        'delay_ms': numeric(r.get('delay_added')),
        'start_delay_ms': numeric(r.get('client_start_delay_ms')),
        'workload_mb': numeric(r.get('client_file_size_megabytes')),
        'cca': ((r.get('congestion_control_algorithms') or {}).get('name') or '').strip().lower(),
    } for r in runs]
    clients.sort(key=lambda c: c['client_number'] or 0)
    n = numeric(parent.get('number_of_clients'))
    settings = {
        'number_of_clients': n, 'rate_mbps': numeric(parent.get('bottleneck_rate_megabit')),
        'buffer_kib': numeric(parent.get('queue_buffer_size_kilobyte')),
        'snapshot_ms': numeric(parent.get('snapshot_length_ms')),
        'topology': parent.get('topology'), 'topology_config': parent.get('topology_config'),
        'clients': [{k: v for k, v in c.items() if k != 'cca'} for c in clients],
        'launch': {k: v for k, v in (job or {}).items() if k not in METADATA},
    }
    settings['launch'].setdefault('loss_pct', 0)
    reasons = []
    if not job or job.get('script') not in RUNNERS:
        reasons.append('Runner configuration unavailable or unsupported')
    if settings['topology'] != 'single-bottleneck':
        reasons.append('Single-bottleneck configuration required')
    if not n or n != len(clients) or any(c['client_number'] != i + 1 for i, c in enumerate(clients)):
        reasons.append('Incomplete or duplicate client configuration')
    for name in ('rate_mbps', 'snapshot_ms', 'buffer_kib'):
        if settings[name] is None or settings[name] < 0 or (name != 'buffer_kib' and settings[name] == 0):
            reasons.append(f'Missing or invalid {name}')
    if any(c['delay_ms'] is None or c['delay_ms'] < 0 or c['start_delay_ms'] is None or c['start_delay_ms'] < 0 or c['workload_mb'] is None or c['workload_mb'] <= 0 or not c['cca'] for c in clients):
        reasons.append('Missing or invalid client settings')
    cca = clients[0]['cca'] if clients else None
    if cca not in ('bbr', 'cubic') or any(c['cca'] != cca for c in clients):
        reasons.append('Homogeneous BBR or CUBIC competition required')
    expected = {
        'num_clients': n, 'client_delays_ms': [c['delay_ms'] for c in clients],
        'client_start_delays_ms': [c['start_delay_ms'] for c in clients],
        'client_file_sizes_mbytes': [c['workload_mb'] for c in clients],
        'client_ccas': [c['cca'] for c in clients],
        'bottleneck_all_client_rate_mbit': settings['rate_mbps'],
        'bottleneck_buffer_kbytes': settings['buffer_kib'], 'topology': settings['topology'],
    }
    if job and any(k in job and job[k] != v for k, v in expected.items()):
        reasons.append('Stored results conflict with launch configuration')
    return {'eligible': not reasons, 'reasons': reasons, 'cca': cca, 'settings': settings}


def compare_validity(first, second):
    """Two parent runs are at most one observation per arm, never replicated trials."""
    result = {
        'configuration_matched': False, 'algorithm_effect_supported': False,
        'confidence_interval': None, 'parent_run_repetitions_per_algorithm': None,
        'unit': 's', 'client_fct_deltas': [], 'reasons': [],
        'interpretation': 'Descriptive comparison only. Do not attribute pooled or unmatched differences to the algorithms. Client flows and snapshots are not independent repetitions.',
    }
    a, b = first.get('comparison_configuration'), second.get('comparison_configuration')
    if not a or not b:
        result['reasons'].append('Configuration analysis unavailable; fetch both runs again')
        return result
    for label, config in [('run_1', a), ('run_2', b)]:
        result['reasons'].extend(f'{label}: {reason}' for reason in config['reasons'])
    if first['parent_run']['id'] == second['parent_run']['id']:
        result['reasons'].append('The same parent run is not an independent comparison')
    if a['cca'] == b['cca']:
        result['reasons'].append('Both runs use the same algorithm')
    result['differing_configuration_fields'] = [key for key in a['settings'] if a['settings'][key] != b['settings'].get(key)]
    if result['differing_configuration_fields']:
        result['reasons'].append('Non-CCA configurations differ; do not report an algorithm effect')
    if result['reasons']:
        return result
    result['configuration_matched'] = True
    result['parent_run_repetitions_per_algorithm'] = {a['cca']: 1, b['cca']: 1}
    result['reasons'].append('Only one parent run per algorithm; confidence interval and causal attribution unavailable')
    result['reasons'].append('No recorded trial pairing/randomization or guaranteed runner/kernel revision match')
    # Standardize every contrast as CUBIC minus BBR, regardless of tool argument order.
    left, right = (first, second) if a['cca'] == 'bbr' else (second, first)
    right_clients = {c['client_number']: c for c in right['clients']}
    for client in left['clients']:
        other = right_clients.get(client['client_number'], {})
        x, y = numeric(client.get('flow_completion_time_ms')), numeric(other.get('flow_completion_time_ms'))
        if x is None or y is None or x <= 0 or y <= 0:
            result['reasons'].append(f'Client {client["client_number"]}: FCT unavailable; no delta')
            continue
        result['client_fct_deltas'].append({'client_number': client['client_number'], 'cubic_minus_bbr_seconds': round((y - x) / 1000, 6)})
    return result
