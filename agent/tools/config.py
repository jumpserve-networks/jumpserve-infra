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


@tool
def list_configs() -> list[dict]:
    """List all saved benchmark configurations that can be reused."""
    key = _get_supabase_key()
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/benchmark_configs?order=created_at.desc&select=id,name,description,config",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


@tool
def save_config(name: str, description: str, config: dict) -> dict:
    """Save a benchmark configuration for future reuse.

    Args:
        name: Short name for the config (e.g. "2-client cubic vs bbr 100Mbit")
        description: Brief description of what this config tests
        config: The benchmark configuration object with keys: num_clients, client_ccas, client_delays_ms, client_file_sizes_mbytes, client_start_delays_ms, bottleneck_all_client_rate_mbit, bottleneck_buffer_kbytes, script
    """
    key = _get_supabase_key()
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/benchmark_configs",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        json={
            "name": name,
            "description": description,
            "config": config,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data[0] if data else {"status": "saved"}
