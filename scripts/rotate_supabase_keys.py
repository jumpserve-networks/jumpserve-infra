#!/usr/bin/env python3
"""Rotate only JumpServe API keys without printing or persisting secret values.

Use prepare to create replacement keys and test them. AWS installation and legacy
revocation are separate operations, so callers can coordinate deployment first.
"""
import argparse
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request

from audit_supabase_security import PROJECT, management

ROOT = Path(__file__).resolve().parents[1]
KEY_NAMES = {"publishable": "jumpserve_web_20260921", "secret": "jumpserve_backend_20260921"}


def keys(create=False):
    existing = management("api-keys?reveal=true")
    selected = {}
    for kind, name in KEY_NAMES.items():
        key = next((item for item in existing if item.get("name") == name and item.get("type") == kind), None)
        if key is None and create:
            payload = {"type": kind, "name": name}
            if kind == "secret":
                payload["secret_jwt_template"] = {"role": "service_role"}
            key = management("api-keys?reveal=true", payload, "POST")
        if not key or key.get("disabled") or not key.get("api_key", "").startswith("sb_" + kind + "_"):
            raise RuntimeError(f"Active replacement {kind} key unavailable")
        selected[kind] = key["api_key"]
    return selected


def probe(key, bearer=None, path="/rest/v1/emulated_parent_runs?select=id&limit=0"):
    headers = {"apikey": key}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(f"https://{PROJECT}.supabase.co" + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context(cafile="/etc/ssl/cert.pem")) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def aws(service, operation, payload):
    # AWS CLI may read paramfiles twice; a pipe cannot reliably supply them.
    # NamedTemporaryFile is mode 0600, lives in ignored workspace artifacts, and
    # is removed even on failure. Secret values never appear in process args.
    artifacts = ROOT / ".test-artifacts"
    artifacts.mkdir(exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=artifacts, suffix=".json") as params:
        json.dump(payload, params)
        params.flush()
        result = subprocess.run(
            ["aws", service, operation, "--region", "us-east-1", "--cli-input-json", "file://" + params.name, "--output", "json"],
            capture_output=True, text=True,
        )
    if result.returncode:
        raise RuntimeError(f"AWS {service} {operation} failed (output suppressed to protect credentials)")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def prepare():
    replacement = keys(create=True)
    for kind, key in replacement.items():
        for bearer in [None, key]:
            code = probe(key, bearer)
            if code != 200:
                raise RuntimeError(f"Replacement {kind} probe returned {code}")
        print(f"Replacement {kind} key created and read-only compatibility checks passed.")
    config_path = ROOT / "cdk.json"
    config = json.loads(config_path.read_text())
    config["context"]["supabaseAnonKey"] = replacement["publishable"]
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    env_file = ROOT.parent / "jumpserve-front-end/.env.local"
    if env_file.exists():
        lines = env_file.read_text().splitlines()
        lines = [f'NEXT_PUBLIC_SUPABASE_ANON_KEY={replacement["publishable"]}' if line.startswith("NEXT_PUBLIC_SUPABASE_ANON_KEY=") else line for line in lines]
        env_file.write_text("\n".join(lines) + "\n")
    print("Updated public CDK configuration and local frontend publishable key.")


def install():
    replacement = keys()
    identity = aws("sts", "get-caller-identity", {})
    if identity["Account"] != "395567831870":
        raise RuntimeError("Refusing key installation outside the JumpServe AWS account")
    launcher = "JumpServeBenchmarkStack-LaunchBenchmarkFn5833EFAD-L6HWyzv2tgwl"
    if aws("lambda", "get-function-concurrency", {"FunctionName": launcher}).get("ReservedConcurrentExecutions") != 0:
        raise RuntimeError("Pause the legacy launcher before installing the replacement secret")
    role = "JumpServeBenchmarkStack-BenchmarkInstanceRole1DECDF-BQH1R7m3rBU6"
    aws("iam", "put-role-policy", {"RoleName": role, "PolicyName": "DenyDatabaseCredentials",
        "PolicyDocument": json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Deny", "Action": ["secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue"], "Resource": "*"}]})})
    aws("secretsmanager", "put-secret-value", {"SecretId": "jumpserve/supabase-service-key", "SecretString": replacement["secret"]})
    print("Replaced the backend key in Secrets Manager; benchmark EC2 is denied secret reads.")
    functions = aws("lambda", "list-functions", {})["Functions"]
    for function in functions:
        name = function["FunctionName"]
        if not name.startswith(("JumpServeBenchmarkStack-", "JumpServeAgentStack-")):
            continue
        config = aws("lambda", "get-function-configuration", {"FunctionName": name})
        env = config.get("Environment", {}).get("Variables", {})
        if env.get("SUPABASE_URL", "").rstrip("/") != f"https://{PROJECT}.supabase.co":
            continue
        if "SUPABASE_ANON_KEY" in env:
            env["SUPABASE_ANON_KEY"] = replacement["publishable"]
        env["SUPABASE_KEY_ROTATION"] = "20260921"
        aws("lambda", "update-function-configuration", {"FunctionName": name, "RevisionId": config["RevisionId"], "Environment": {"Variables": env}})
        print("Refreshed Lambda credential consumer:", name)
    app_id = "d24jvguj7brnkj"
    app = aws("amplify", "get-app", {"appId": app_id})["app"]
    env = app.get("environmentVariables", {})
    env["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = replacement["publishable"]
    aws("amplify", "update-app", {"appId": app_id, "environmentVariables": env})
    branch = aws("amplify", "get-branch", {"appId": app_id, "branchName": "main"})["branch"]
    env = branch.get("environmentVariables", {})
    env["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = replacement["publishable"]
    aws("amplify", "update-branch", {"appId": app_id, "branchName": "main", "environmentVariables": env})
    job = aws("amplify", "start-job", {"appId": app_id, "branchName": "main", "jobType": "RELEASE"})
    print("Amplify rebuild started:", job["jobSummary"]["jobId"])


def revoke():
    legacy = next(key["api_key"] for key in management("api-keys?reveal=true") if key["id"] == "service_role")
    try:
        management("api-keys/legacy?enabled=false", method="PUT")
    except RuntimeError as error:
        if "HTTP 422" not in str(error) or "were already disabled" not in str(error):
            raise
    replacement = keys()
    for description, key, bearer in [("legacy API key", legacy, legacy), ("legacy bearer with publishable key", replacement["publishable"], legacy)]:
        code = probe(key, bearer)
        if code not in (401, 403):
            raise RuntimeError(f"Revocation verification failed for {description}: HTTP {code}")
        print(f"Rejected {description}: HTTP {code}")
    for kind, key in replacement.items():
        if probe(key) != 200:
            raise RuntimeError(f"Replacement {kind} key stopped working")
    print("Legacy keys disabled; replacement keys still work.")


def signing_status():
    for key in management("config/auth/signing-keys")["keys"]:
        print({field: key.get(field) for field in ("id", "algorithm", "status", "updated_at")})


def rotate_signing():
    current = management("config/auth/signing-keys")["keys"]
    if not current:
        management("config/auth/signing-keys/legacy", {}, "POST")
        current = management("config/auth/signing-keys")["keys"]
    if any(key["status"] == "in_use" and key["algorithm"] == "ES256" for key in current):
        print("Asymmetric signing key already in use.")
        return
    standby = next((key for key in current if key["status"] == "standby" and key["algorithm"] == "ES256"), None)
    if standby is None:
        standby = management("config/auth/signing-keys", {"algorithm": "ES256"}, "POST")
    management("config/auth/signing-keys/" + standby["id"], {"status": "in_use"}, "PATCH")
    print("Rotated authentication signing to ES256. Legacy signing still requires revocation.")


def revoke_signing():
    current = management("config/auth/signing-keys")["keys"]
    if not any(key["status"] == "in_use" and key["algorithm"] == "ES256" for key in current):
        raise RuntimeError("Rotate to ES256 before revoking legacy signing")
    legacy = management("config/auth/signing-keys/legacy")
    if legacy["status"] != "revoked":
        management("config/auth/signing-keys/" + legacy["id"], {"status": "revoked"}, "PATCH")
    revoke()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install", "revoke", "signing-status", "rotate-signing", "revoke-signing"))
    action = parser.parse_args().action
    {"prepare": prepare, "install": install, "revoke": revoke, "signing-status": signing_status,
     "rotate-signing": rotate_signing, "revoke-signing": revoke_signing}[action]()
