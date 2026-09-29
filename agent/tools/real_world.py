"""Real-world chat reads public measurement relations, never orchestration secrets."""
import re
from uuid import UUID
from strands import tool
from database import Database
from real_world_analysis import public_job, summarize_report, compare_reports, RESULT_PATH


def _id(value):
    return str(UUID(value))


def _bounded(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}')
    return value


def _read(database, identifier):
    runs = database.get('real_world_runs', params={'job_id': f'eq.{identifier}', 'select': 'record', 'limit': 1})
    if not runs:
        return None, None
    rows = database.get('real_world_reports', params={'job_id': f'eq.{identifier}', 'select': 'report', 'limit': 1})
    return runs[0]['record'], rows[0]['report'] if rows else None


def _result(database, identifier):
    job, report = _read(database, identifier)
    if not job:
        return {'error': 'Real-world test not found', 'job_id': identifier}
    if not report:
        return {'job': public_job(job), 'report_status': 'unavailable', 'results_url': f'{RESULT_PATH}/{identifier}',
                'warnings': ['No saved normalized report exists yet. Missing measurements are unavailable, not zero.']}
    return summarize_report(report, job)


@tool
def search_real_world_tests(limit: int = 10, offset: int = 0, cca: str | None = None, status: str | None = None) -> dict:
    """List a bounded page of real EC2 test records, newest first, from Supabase.

    Args:
        limit: Page size, 1 to 25.
        offset: Number of records already read, 0 to 10000.
        cca: Optional exact server algorithm, such as cubic or bbr.
        status: Optional exact recorded test status, including failed tests.
    """
    limit = _bounded(limit, 1, 25, 'limit')
    offset = _bounded(offset, 0, 10000, 'offset')
    params = {'select': 'record', 'order': 'created_at.desc,job_id.desc', 'limit': limit + 1, 'offset': offset}
    for name, value, column in [('cca', cca, 'config->>cca'), ('status', status, 'status')]:
        if value is not None:
            if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', value):
                raise ValueError(f'Invalid {name}')
            params[column] = f'eq.{value}'
    rows = Database().get('real_world_runs', params=params)
    return {'tests': [public_job(row['record']) for row in rows[:limit]], 'offset': offset,
            'next_offset': offset + limit if len(rows) > limit else None,
            'coverage': 'This page of recorded tests only; configurations are not measured results. Use get_real_world_results for measurements.'}


@tool
def get_real_world_results(job_id: str) -> dict:
    """Read a real-world test's saved measurements, configuration, warnings and provenance.

    Args:
        job_id: Real-world test UUID, never an emulated parent-run number.
    """
    return _result(Database(), _id(job_id))


@tool
def get_real_world_trace(job_id: str, metric: str, receiver: str = '', offset: int = 0, limit: int = 100) -> dict:
    """Read an unsampled page of a saved trace, with explicit clock and coverage.

    Args:
        job_id: Real-world test UUID.
        metric: throughput, tcp, or queue.
        receiver: Exact receiver name for throughput/tcp, e.g. receiver-1; empty for queue.
        offset: Zero-based starting sample, 0 to 100000.
        limit: Page size, 1 to 200. Read further pages before whole-trace conclusions.
    """
    identifier = _id(job_id)
    offset, limit = _bounded(offset, 0, 100000, 'offset'), _bounded(limit, 1, 200, 'limit')
    if metric not in ('throughput', 'tcp', 'queue'):
        raise ValueError('metric must be throughput, tcp, or queue')
    job, report = _read(Database(), identifier)
    if not job or not report:
        return {'error': 'Saved trace unavailable', 'job_id': identifier}
    fields = {'throughput': 'start,seconds,duration_seconds,received_bytes,mbit_per_second',
              'tcp': 'seconds,rtt_ms,cwnd_bytes', 'queue': 'seconds,backlog_bytes,queue_delay_ms,drops,sent_bytes'}
    if metric == 'queue':
        points = report.get('queue') or []
    else:
        rows = [row for row in report.get('receivers', []) if row.get('name') == receiver]
        if not rows:
            return {'error': 'Receiver not found', 'job_id': identifier}
        points = rows[0].get(metric) or []
    from real_world_analysis import pick
    return {'job_id': identifier, 'metric': metric, 'receiver': receiver if metric != 'queue' else 'bottleneck',
            'report_status': summarize_report(report, job)['report_status'], 'analysis_version': report.get('analysis_version'),
            'clock': 'seconds into this receiver transfer' if metric == 'throughput' else 'seconds since scheduled start',
            'units': {'mbit_per_second': 'Mbit/s', 'rtt_ms': 'ms', 'queue_delay_ms': 'ms; estimated drain time',
                      'cwnd_bytes': 'bytes', 'backlog_bytes': 'bytes', 'drops': 'cumulative packets'},
            'scheduled_duration_seconds': job['config']['duration_seconds'],
            'points': [pick(row, fields[metric]) for row in points[offset:offset + limit]],
            'offset': offset, 'total_points': len(points),
            'next_offset': offset + limit if offset + limit < len(points) else None,
            'warnings': report.get('warnings', []),
            'coverage': 'Exact recorded page, not a whole-trace sample. Nulls and missing intervals are unavailable; traces may include a post-test tail.'}


@tool
def compare_real_world_tests(job_ids: list[str], baseline_cca: str, comparison_cca: str,
                             metric: str = 'combined_mean_mbit_per_second') -> dict:
    """Compare whole-test outcomes within complete recorded configuration blocks only.

    Args:
        job_ids: Two to twenty selected real-world UUIDs. Duplicate IDs count once.
        baseline_cca: Baseline server CCA.
        comparison_cca: Different comparison server CCA.
        metric: combined_mean_mbit_per_second or jain_fairness.
    """
    if not isinstance(job_ids, list) or not 2 <= len(job_ids) <= 20:
        raise ValueError('Select 2 to 20 test IDs per comparison')
    identifiers = [_id(value) for value in job_ids]
    database, reports, missing, cache = Database(), [], [], {}
    for identifier in identifiers:
        if identifier not in cache:
            cache[identifier] = _result(database, identifier)
        result = cache[identifier]
        if 'error' in result:
            missing.append({'job_id': identifier, 'reason': result['error']})
        else:
            reports.append(result)
    result = compare_reports(reports, baseline_cca, comparison_cca, metric)
    result['excluded'].extend(missing)
    return result
