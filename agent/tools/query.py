import json
import os
import httpx
from strands import tool

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_supabase_key: str | None = None


def _get_supabase_key() -> str:
    global _supabase_key
    if _supabase_key:
        return _supabase_key
    import boto3
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=os.environ["SUPABASE_SECRET_ARN"])
    _supabase_key = resp["SecretString"]
    return _supabase_key


def _supabase_get(path: str) -> list | dict:
    key = _get_supabase_key()
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


@tool
def list_jobs(limit: int = 10, status_filter: str | None = None) -> list[dict]:
    """List recent benchmark jobs with their status and configuration.

    Args:
        limit: Maximum number of jobs to return (default 10)
        status_filter: Optional status to filter by (pending, launching, installing, cloning, running, completed, failed, terminated, cancelled)
    """
    path = f"benchmark_jobs?order=created_at.desc&limit={limit}&select=id,created_at,status,config,parent_run_id,error_message,requested_by"
    if status_filter:
        path += f"&status=eq.{status_filter}"
    jobs = _supabase_get(path)
    # Summarize config for readability
    for job in jobs:
        if job.get("config"):
            c = job["config"]
            job["config_summary"] = (
                f"{c.get('num_clients', '?')} clients, "
                f"CCAs: {','.join(c.get('client_ccas', []))}, "
                f"delays: {c.get('client_delays_ms')}ms, "
                f"rate: {c.get('bottleneck_all_client_rate_mbit')} Mbit, "
                f"buffer: {c.get('bottleneck_buffer_kbytes')} KB"
            )
    return jobs


@tool
def get_job_status(job_id: str) -> dict:
    """Get detailed status of a specific benchmark job.

    Args:
        job_id: The UUID of the benchmark job
    """
    jobs = _supabase_get(f"benchmark_jobs?id=eq.{job_id}&select=*")
    if not jobs:
        return {"error": "Job not found"}
    return jobs[0]


@tool
def get_run_results(parent_run_id: int) -> dict:
    """Get the results of a completed benchmark run including per-client metrics.

    Args:
        parent_run_id: The ID of the parent run (from emulated_parent_runs table)
    """
    # Get parent run metadata
    parent = _supabase_get(f"emulated_parent_runs?id=eq.{parent_run_id}&select=*")
    if not parent:
        return {"error": "Parent run not found"}
    parent = parent[0]

    # Get per-client runs
    runs = _supabase_get(
        f"emulated_runs?emulated_parent_run_id=eq.{parent_run_id}"
        f"&select=id,client_number,delay_added,client_file_size_megabytes,"
        f"client_start_delay_ms,flow_completion_time_ms,"
        f"congestion_control_algorithm_id,congestion_control_algorithms(name)"
    )

    # Get snapshot stats (summarized — too many rows for full data)
    results = []
    for run in runs:
        stats = _supabase_get(
            f"emulated_snapshot_stats?emulated_run_id=eq.{run['id']}"
            f"&select=megabits_per_second,round_trip_time_ms,bottleneck_queuing_delay_ms,"
            f"congestion_window_bytes,in_flight_packets"
            f"&order=snapshot_index"
        )
        # Compute summary statistics
        if stats:
            throughputs = [float(s["megabits_per_second"]) for s in stats if s["megabits_per_second"]]
            rtts = [float(s["round_trip_time_ms"]) for s in stats if s["round_trip_time_ms"]]
            cca_name = run.get("congestion_control_algorithms", {}).get("name", "unknown")

            results.append({
                "client_number": run["client_number"],
                "cca": cca_name,
                "delay_ms": run["delay_added"],
                "file_size_mb": run["client_file_size_megabytes"],
                "flow_completion_time_ms": run["flow_completion_time_ms"],
                "throughput_avg_mbps": round(sum(throughputs) / len(throughputs), 2) if throughputs else None,
                "throughput_max_mbps": round(max(throughputs), 2) if throughputs else None,
                "rtt_avg_ms": round(sum(rtts) / len(rtts), 2) if rtts else None,
                "rtt_p95_ms": round(sorted(rtts)[int(len(rtts) * 0.95)] if rtts else 0, 2),
                "num_snapshots": len(stats),
            })

    return {
        "parent_run": parent,
        "clients": results,
    }


@tool
def compare_runs(parent_run_id_1: int, parent_run_id_2: int) -> dict:
    """Compare the results of two benchmark runs side-by-side.

    Args:
        parent_run_id_1: The ID of the first parent run
        parent_run_id_2: The ID of the second parent run
    """
    run1 = get_run_results.tool_handler(parent_run_id=parent_run_id_1)
    run2 = get_run_results.tool_handler(parent_run_id=parent_run_id_2)

    return {
        "run_1": run1,
        "run_2": run2,
    }


@tool
def search_runs(
    cca: str | None = None,
    min_delay_ms: int | None = None,
    max_delay_ms: int | None = None,
    min_rate_mbit: int | None = None,
    max_rate_mbit: int | None = None,
    num_clients: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search for benchmark parent runs by parameters.

    Args:
        cca: Filter by congestion control algorithm name (e.g. "cubic", "bbr")
        min_delay_ms: Minimum client delay in milliseconds
        max_delay_ms: Maximum client delay in milliseconds
        min_rate_mbit: Minimum bottleneck rate in Mbit/s
        max_rate_mbit: Maximum bottleneck rate in Mbit/s
        num_clients: Filter by number of clients
        limit: Maximum number of results (default 10)
    """
    path = (
        f"emulated_parent_runs?order=created_at.desc&limit={limit}"
        f"&select=id,created_at,number_of_clients,bottleneck_rate_megabit,"
        f"queue_buffer_size_kilobyte,snapshot_length_ms"
    )
    if num_clients:
        path += f"&number_of_clients=eq.{num_clients}"
    if min_rate_mbit:
        path += f"&bottleneck_rate_megabit=gte.{min_rate_mbit}"
    if max_rate_mbit:
        path += f"&bottleneck_rate_megabit=lte.{max_rate_mbit}"

    results = _supabase_get(path)
    return results
