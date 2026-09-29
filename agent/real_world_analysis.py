"""Bounded, read-only evidence for real-world chat; one whole test is a replicate."""
import hashlib
import json
import math
import statistics

MIN_REPEATS = 5
BOOTSTRAP_SAMPLES = 2000
METRICS = {'combined_mean_mbit_per_second': 'Mbit/s', 'jain_fairness': 'unitless'}
RESULT_PATH = '/module/congestion-control-real-world/test-results'


def pick(value, keys):
    return {key: value.get(key) for key in keys.split(',')} if isinstance(value, dict) else {}


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def public_job(job):
    result = pick(job, 'job_id,status,created_at,updated_at,started_at,finished_at,runtime_revision,error')
    config = job.get('config') or {}
    result['config'] = pick(config, 'cca,duration_seconds,rate_mbit,buffer_kbytes,notes')
    placement = lambda value: pick(value, 'region,zone_id,instance_type')
    result['config'].update(server=placement(config.get('server')), bottleneck=placement(config.get('bottleneck')),
                            receivers=[placement(value) for value in config.get('receivers', [])])
    # Public placements/software are sufficient; no instance addresses or user identities.
    result['nodes'] = [pick(value, 'name,role,region,zone_id,instance_type,image_id') for value in job.get('nodes', [])]
    return result


def summarize_report(report, current_job):
    job = report.get('job') or {}
    stale = job.get('updated_at') != current_job.get('updated_at') or job.get('status') != current_job.get('status')
    receivers = []
    for receiver in report.get('receivers', []):
        row = pick(receiver, 'name,placement,throughput_intervals,tcp_samples')
        for key in ('received_bytes', 'duration_seconds', 'mean_mbit_per_second', 'retransmits', 'preflight_rtt_ms'):
            row[key] = number(receiver.get(key))
        row['rtt'] = {key: number((receiver.get('rtt') or {}).get(key)) for key in ('samples', 'median', 'p95')}
        receivers.append(row)
    summary = {key: number((report.get('summary') or {}).get(key)) for key in (
        'combined_mean_mbit_per_second', 'jain_fairness', 'received_bytes', 'observed_queue_drops', 'start_skew_ms')}
    summary['queue_delay'] = {key: number((report.get('summary', {}).get('queue_delay') or {}).get(key))
                              for key in ('samples', 'median', 'p95')}
    warnings = list(report.get('warnings') or [])
    if stale:
        warnings.append('Saved analysis predates the current test record. Do not treat it as the final result or use it in comparisons.')
    return {
        'job': public_job(current_job), 'report_status': 'stale' if stale else 'available',
        'report_job_status': job.get('status'), 'report_job_updated_at': job.get('updated_at'),
        'results_url': f"{RESULT_PATH}/{current_job['job_id']}",
        'analysis_version': report.get('analysis_version'), 'summary': summary, 'receivers': receivers,
        'comparison': pick(report.get('comparison'), 'eligible,exclusions,key,configuration'),
        'warnings': warnings,
        'provenance': [pick(row, 'name,kernel,iperf_version,image_id,success') for row in report.get('provenance', [])],
        'sources': [pick(row, 'name,sha256,version_id,bytes') for row in report.get('sources', [])],
        'trace_access': 'Use get_real_world_trace for bounded pages of recorded measurements; no traces are sampled into this summary.',
    }


def _quantile(values, fraction):
    index = (len(values) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def bootstrap(left, right=None):
    """Match the site's seeded percentile bootstrap of independent whole tests."""
    if len(left) < MIN_REPEATS or right is not None and len(right) < MIN_REPEATS:
        return None
    state = 0x20260920

    def draw(values):
        nonlocal state
        sample = []
        for _ in values:
            state = (1664525 * state + 1013904223) & 0xffffffff
            sample.append(values[math.floor(state / 4294967296 * len(values))])
        return statistics.median(sample)

    draws = []
    for _ in range(BOOTSTRAP_SAMPLES):
        baseline = draw(left)
        draws.append(draw(right) - baseline if right is not None else baseline)
    draws.sort()
    return {'low': _quantile(draws, .025), 'high': _quantile(draws, .975)}


def compare_reports(reports, baseline, comparison, metric):
    if metric not in METRICS or not baseline or not comparison or baseline == comparison:
        raise ValueError('Choose two different CCAs and a supported outcome')
    groups, excluded, seen = {}, [], set()
    for report in sorted(reports, key=lambda r: r['job']['job_id']):
        job = report['job']
        identifier, cca = job['job_id'], job['config'].get('cca')
        validity = report.get('comparison') or {}
        value = number(report.get('summary', {}).get(metric))
        reason = None
        if identifier in seen:
            reason = 'Duplicate test ID; counted only once'
        elif report.get('report_status') != 'available' or job.get('status') != 'completed':
            reason = 'Only completed tests with current saved reports are eligible'
        elif not validity.get('eligible') or not validity.get('key') or not validity.get('configuration') or not report.get('analysis_version'):
            reason = '; '.join(validity.get('exclusions') or []) or 'Comparison provenance is incomplete'
        elif cca not in (baseline, comparison):
            reason = 'Algorithm is outside the selected contrast'
        elif value is None:
            reason = 'Selected outcome is unavailable'
        seen.add(identifier)
        if reason:
            excluded.append({'job_id': identifier, 'reason': reason})
            continue
        configuration = {'version': report['analysis_version'], 'configuration': validity['configuration']}
        key = json.dumps(configuration, sort_keys=True, separators=(',', ':'))
        group = groups.setdefault(key, {'configuration': configuration, 'baseline': [], 'comparison': []})
        group['baseline' if cca == baseline else 'comparison'].append((identifier, value))

    def cohort(rows):
        values = [row[1] for row in rows]
        return {'count': len(rows), 'test_ids': [row[0] for row in rows], 'values': values,
                'median': statistics.median(values) if values else None, 'interval': bootstrap(values)}

    blocks = []
    for key, group in groups.items():
        left, right = cohort(group['baseline']), cohort(group['comparison'])
        delta = right['median'] - left['median'] if left['count'] and right['count'] else None
        blocks.append({'key': hashlib.sha256(key.encode()).hexdigest(), 'configuration': group['configuration'],
                       'baseline': left, 'comparison': right, 'delta': delta,
                       'interval': bootstrap(left['values'], right['values'])})
    return {'baseline_cca': baseline, 'comparison_cca': comparison, 'metric': metric, 'unit': METRICS[metric],
            'delta_definition': 'comparison minus baseline', 'blocks': blocks, 'excluded': excluded,
            'matched_blocks': sum(block['delta'] is not None for block in blocks),
            'method': {'replication_unit': 'one whole test', 'paired': False, 'pooled': False,
                       'interval': 'pointwise exploratory 95% percentile bootstrap', 'resamples': BOOTSTRAP_SAMPLES,
                       'minimum_tests_per_cca_for_intervals': MIN_REPEATS},
            'limitations': ['Only the explicitly selected tests are compared.',
                            'Matching does not establish randomization, causal effects, route stability, or independent runs.',
                            'Five repeats is a display threshold; sparse/constant data, temporal dependence and multiple comparisons limit inference.']}
