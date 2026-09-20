"""Deterministic, unit-labelled summaries for the research assistant (no I/O)."""
import math

ANALYSIS_VERSION = '2026-09-20.2'
SINGLE_RUNNERS = {
    'netem_cubic_benchmark_hotnets.py', 'netem_cubic_benchmark_nines.py', 'netem_nines.py',
}
MULTI_RUNNER = 'netem_multi_bottleneck.py'


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def rounded(value):
    return round(value, 6) if value is not None else None


def measurement_contract(parent, job_config):
    script = job_config.get('script')
    topology = parent.get('topology') or job_config.get('topology')
    # For imported runs, the documented topology is usable context, but is not
    # proof of the exact historic executable/kernel revision.
    single = script in SINGLE_RUNNERS or (not script and topology == 'single-bottleneck')
    multi = script == MULTI_RUNNER or (not script and topology in ('parking-lot', 'dumbbell'))
    conflict = (single and topology not in (None, 'single-bottleneck')) or (multi and topology not in (None, 'parking-lot', 'dumbbell'))
    if conflict:
        single = multi = False
    known = single or multi
    return {
        'version': ANALYSIS_VERSION,
        'script': script,
        'topology': topology or ('single-bottleneck' if single else None),
        'provenance': 'benchmark_jobs.config' if script else 'documented topology; exact historical runner not recorded',
        'runner_revision': None,
        'conflicting_runner_topology': conflict,
        'kernel_and_bbr_revision': None,
        'delay_parameter': 'added RTT contribution, applied once per round trip' if known else 'unknown',
        'delay_application': 'ACK return path once' if single else ('forward path once' if multi else 'unknown'),
        'delay_multiplier_for_added_rtt': 1 if known else None,
        'delay_is_measured_unloaded_rtt': False,
        'rtt_source': job_config.get('snapshot_metrics_source', 'not recorded') if single else 'unavailable',
        'queue_delay_source': 'stored estimate: backlog_bytes * 8 * 1000 / configured_link_bits_per_second' if single else 'unavailable',
        'buffer_setting_unit': 'KiB (1024 bytes); rounded up to a packet limit' if single else 'unknown',
        'tcp_and_queue_snapshots_supported': True if single else (False if multi else None),
    }


def metric(rows, field, unit, *, zero_unavailable=False, supported=True):
    result = {'unit': unit, 'scope': 'all returned snapshots; unweighted sample statistics',
              'mean': None, 'min': None, 'max': None, 'p95': None,
              'valid_samples': 0, 'zero_samples': 0, 'missing_samples': 0,
              'invalid_samples': 0, 'zero_unavailable_samples': 0,
              'availability': 'available' if supported else 'unsupported_or_unknown'}
    if not supported:
        return result
    values = []
    for row in rows:
        raw = row.get(field)
        value = number(raw)
        if raw is None:
            result['missing_samples'] += 1
        elif value is None or value < 0:
            result['invalid_samples'] += 1
        elif value == 0 and zero_unavailable:
            result['zero_unavailable_samples'] += 1
        else:
            values.append(value)
    result['valid_samples'] = len(values)
    result['zero_samples'] = values.count(0)
    if values:
        ordered = sorted(values)
        result.update(mean=rounded(math.fsum(values) / len(values)), min=rounded(ordered[0]),
                      max=rounded(ordered[-1]), p95=rounded(ordered[math.ceil(len(values) * .95) - 1]))
    else:
        result['availability'] = 'unavailable'
    if field == 'megabits_per_second':
        positive = [value for value in values if value > 0]
        result['nonzero_sample_mean'] = rounded(math.fsum(positive) / len(positive)) if positive else None
        result['nonzero_sample_count'] = len(positive)
        result['nonzero_mean_scope'] = 'diagnostic only; excludes zeros and may use different windows per client'
    return result


def timed_throughput(rows):
    """Rates summarize intervals ending at elapsed_microseconds, beginning at 0."""
    previous = 0.0
    total = 0.0
    boundaries = []
    for row in rows:
        end = number(row.get('elapsed_microseconds'))
        rate = number(row.get('megabits_per_second'))
        if end is None or end <= previous or rate is None or rate < 0:
            return None, None
        total += rate * (end - previous)
        boundaries.append(end)
        previous = end
    return (rounded(total / previous), boundaries) if previous > 0 else (None, None)


def summarize_run(parent, runs, snapshots, job_config=None, incomplete_run_ids=()):
    contract = measurement_contract(parent, job_config or {})
    clients, warnings, timings = [], [], []
    buffer_kib = number(parent.get('queue_buffer_size_kilobyte'))
    capacity_mbps = number(parent.get('bottleneck_rate_megabit'))
    nominal_drain_ms = None
    if (contract['tcp_and_queue_snapshots_supported'] is True and
            buffer_kib is not None and buffer_kib > 0 and
            capacity_mbps is not None and capacity_mbps > 0):
        nominal_drain_ms = rounded(buffer_kib * 1024 * 8 / (capacity_mbps * 1000))

    def warn(code, detail, client=None):
        warnings.append({'code': code, 'client_number': client, 'detail': detail})

    if not contract['script']:
        warn('runner_provenance_incomplete', contract['provenance'])
    if contract['conflicting_runner_topology']:
        warn('conflicting_provenance', 'Runner and topology disagree; delay and instrumentation assumptions are unavailable.')
    if contract['delay_multiplier_for_added_rtt'] is None:
        warn('unknown_delay_semantics', 'Do not derive base RTT or queue delay from this configuration.')
    if contract['tcp_and_queue_snapshots_supported'] is False:
        warn('unsupported_metrics', 'This multi-bottleneck runner writes placeholder zeros for TCP and queue metrics.')
    if contract['topology'] == 'parking-lot':
        warn('experimental_topology', 'Current parking-lot runner only shapes the first bottleneck.')

    for run in runs:
        client_no = run['client_number']
        rows = snapshots.get(str(run['id']), [])
        supported = contract['tcp_and_queue_snapshots_supported'] is True
        metrics = {
            'throughput': metric(rows, 'megabits_per_second', 'Mbps'),
            'rtt': metric(rows, 'round_trip_time_ms', 'ms', zero_unavailable=True, supported=supported),
            'queue_delay': metric(rows, 'bottleneck_queuing_delay_ms', 'ms', supported=supported),
            'congestion_window': metric(rows, 'congestion_window_bytes', 'bytes', zero_unavailable=True, supported=supported),
            'in_flight': metric(rows, 'in_flight_packets', 'packets', supported=supported),
        }
        for name, summary in metrics.items():
            if summary['invalid_samples']:
                warn('invalid_measurement', f'{name}: {summary["invalid_samples"]} negative or non-finite/non-numeric samples excluded; investigate, do not explain away or clamp.', client_no)
        weighted, boundaries = timed_throughput(rows)
        metrics['throughput']['time_weighted_mean'] = weighted
        metrics['throughput']['time_weighted_scope'] = 'intervals from elapsed 0 to last sample; includes valid zero throughput; unavailable if timestamps/rates are incomplete'
        timings.append(boundaries)
        added = number(run.get('delay_added')) if contract['delay_multiplier_for_added_rtt'] == 1 else None
        if added is not None and added < 0:
            warn('invalid_configured_delay', 'Configured added delay is negative; interpretation unavailable.', client_no)
            added = None
        if added is not None and metrics['rtt']['min'] is not None and metrics['rtt']['min'] < added:
            warn('rtt_below_configured_added_delay', 'Positive RTT sample below the configured added RTT contribution. Check semantics, provenance and measurement validity; do not invent negative queueing delay or a ramp-up explanation.', client_no)
        if not rows:
            warn('missing_snapshots', 'No measurements available for this client.', client_no)
        if run['id'] in incomplete_run_ids:
            warn('incomplete_snapshots', 'Snapshot safety limit reached; statistics are partial, not full-run results.', client_no)
        clients.append({
            'run_id': run['id'], 'client_number': client_no,
            'cca': (run.get('congestion_control_algorithms') or {}).get('name', 'unknown'),
            'cca_revision': 'not recorded',
            'configured_delay_ms': number(run.get('delay_added')),
            'configured_added_rtt_ms': added,
            'file_size_mb': number(run.get('client_file_size_megabytes')),
            'start_delay_ms': number(run.get('client_start_delay_ms')),
            'flow_completion_time_ms': number(run.get('flow_completion_time_ms')),
            'num_snapshots': len(rows), 'complete_snapshot_fetch': run['id'] not in incomplete_run_ids,
            'window': {'first_sample_elapsed_ms': rounded(number(rows[0].get('elapsed_microseconds')) / 1000) if rows and number(rows[0].get('elapsed_microseconds')) is not None else None,
                       'last_sample_elapsed_ms': rounded(number(rows[-1].get('elapsed_microseconds')) / 1000) if rows and number(rows[-1].get('elapsed_microseconds')) is not None else None},
            'sample_timing_note': 'Aggregate zero/missing counts do not establish which samples occur at startup, during transfer, or after completion.',
            'metrics': metrics,
        })

    fairness = {'available': False, 'scope': 'time-weighted throughput over identical full-run snapshot intervals, including zeros; not isolated concurrent-transfer fairness'}
    expected = number(parent.get('number_of_clients'))
    if (len(clients) >= 2 and len(clients) == expected and not incomplete_run_ids and
            contract['topology'] == 'single-bottleneck' and timings[0] and
            all(timing == timings[0] for timing in timings)):
        rates = [client['metrics']['throughput']['time_weighted_mean'] for client in clients]
        total, squares = math.fsum(rates), math.fsum(rate ** 2 for rate in rates)
        if total > 0:
            n = len(rates)
            stdev = math.sqrt(math.fsum((rate - total / n) ** 2 for rate in rates) / n)
            fairness.update(available=True, jains_index=rounded(total ** 2 / (n * squares)),
                            throughput_ratio=rounded(max(rates) / min(rates)) if min(rates) > 0 else None,
                            throughput_cv=rounded(stdev / (total / n)))
    if not fairness['available']:
        fairness['reason'] = 'Requires all clients, complete matching timestamps and valid throughput at one shared bottleneck.'
    else:
        warn('fairness_window', 'Full-run fairness includes intervals after a client finishes; equal file sizes can mask different completion times. Nonzero-sample averages are not common-window fairness.')
    return {
        'analysis_version': ANALYSIS_VERSION, 'parent_run': parent,
        'measurement_contract': contract, 'clients': clients, 'fairness': fairness,
        'bottleneck_buffer': {
            'nominal_drain_time_ms': nominal_drain_ms,
            'interpretation': 'Configured-capacity approximation, not a strict measured queue-delay upper bound; packet rounding and accounting matter.',
        },
        'warnings': warnings,
        'research_reference': {'title': 'Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays',
                               'url': 'https://doi.org/10.4230/OASIcs.NINeS.2026.27', 'context_version': ANALYSIS_VERSION},
    }
