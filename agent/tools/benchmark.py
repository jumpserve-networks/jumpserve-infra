import json
import os
import httpx
from strands import tool

BENCHMARK_API_URL = os.environ.get("BENCHMARK_API_URL", "")
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


@tool
def run_benchmark(
    num_clients: int,
    client_ccas: list[str],
    client_delays_ms: list[float],
    client_file_sizes_mbytes: list[float],
    bottleneck_rate_mbit: float,
    buffer_size_kbytes: float,
    client_start_delays_ms: list[float] | None = None,
    script: str = "netem_cubic_benchmark_hotnets.py",
    loss_pct: float = 0.0,
) -> dict:
    """Launch a TCP congestion control benchmark on a fresh EC2 instance.

    Args:
        num_clients: Number of clients (1-10)
        client_ccas: List of CCA names per client (e.g. ["cubic", "bbr"])
        client_delays_ms: Per-client network delay in milliseconds
        client_file_sizes_mbytes: Per-client transfer size in megabytes
        bottleneck_rate_mbit: Shared bottleneck link capacity in Mbit/s
        buffer_size_kbytes: Bottleneck queue buffer size in kilobytes
        client_start_delays_ms: Optional per-client flow start delays in ms
        script: Benchmark script to run
        loss_pct: Packet loss percentage (0-100)
    """
    config = {
        "num_clients": num_clients,
        "client_ccas": client_ccas,
        "client_delays_ms": client_delays_ms,
        "client_file_sizes_mbytes": client_file_sizes_mbytes,
        "client_start_delays_ms": client_start_delays_ms or [0] * num_clients,
        "bottleneck_all_client_rate_mbit": bottleneck_rate_mbit,
        "bottleneck_buffer_kbytes": buffer_size_kbytes,
        "snapshot_metrics_source": "kernel",
        "script": script,
    }
    if loss_pct > 0:
        config["loss_pct"] = loss_pct

    resp = httpx.post(
        f"{BENCHMARK_API_URL}/benchmarks",
        json={"config": config},
        timeout=30,
    )
    return resp.json()


@tool
def cancel_benchmark(job_id: str) -> dict:
    """Cancel a running benchmark by terminating its EC2 instance.

    Args:
        job_id: The UUID of the benchmark job to cancel
    """
    resp = httpx.post(
        f"{BENCHMARK_API_URL}/benchmarks/cancel",
        json={"jobId": job_id},
        timeout=15,
    )
    return resp.json()


@tool
def get_benchmark_logs(job_id: str) -> dict:
    """Get the EC2 instance logs for a running or completed benchmark.

    Args:
        job_id: The UUID of the benchmark job
    """
    resp = httpx.get(
        f"{BENCHMARK_API_URL}/benchmarks/logs",
        params={"jobId": job_id},
        timeout=15,
    )
    data = resp.json()
    # Truncate to last 50 lines to fit in context
    events = data.get("events", [])
    if len(events) > 50:
        events = events[-50:]
    return {"events": events, "total_lines": len(data.get("events", []))}
