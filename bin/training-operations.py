"""Fixed operations executed as the JumpServe coordinator user."""

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time


HOME = Path("/home/ec2-user")
RUNTIME = HOME / "jumpserve-batch"
RUNS = HOME / "jumpserve-runs"
SOURCE_DIRECTORIES = {"lib", "scripts", "skills"}
MANIFESTS = {"package.json", "package-lock.json"}
RETAINED_DIRECTORIES = {"node_modules", "pdfs", "answer-keys"}
MAX_ARCHIVE = 16 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
TERMINAL = {"completed", "passed", "stopped", "interrupted"}
AWS_ERRORS = (
    "AccessDenied", "InsufficientInstanceCapacity", "ThrottlingException",
    "RequestLimitExceeded", "VpcLimitExceeded", "VcpuLimitExceeded",
    "VolumeInUse", "AttachmentLimitExceeded", "LimitExceededException",
)
PAPER_ERROR_CODES = (
    ("worker_not_ready", "did not become ready over session manager"),
    ("unsafe_archive_entry", "unsafe stage artifact"),
    ("transfer_limit", "exceeds the transfer limit"),
    ("worker_transfer", "could not retrieve"),
    ("worker_failure", "worker stopped"),
    ("worker_deadline", "timed out"),
    ("invalid_assessment", "bundle does not match"),
    ("invalid_assessment", "bundle contains"),
    ("missing_output", "expected a bounded regular output file"),
    ("invalid_scorecard", "scorecard"),
)


class OperationError(Exception):
    pass


def require(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise OperationError("invalid_request")
    return value


def aws(*arguments):
    return subprocess.run(
        ["aws", "--region", "us-east-1", "--no-cli-pager", *arguments],
        capture_output=True, timeout=40, check=True,
    )


def receipt(bucket, key, payload):
    with tempfile.NamedTemporaryFile() as output:
        output.write(json.dumps(payload, separators=(",", ":")).encode())
        output.flush()
        aws("s3api", "put-object", "--bucket", bucket, "--key", key,
            "--content-type", "application/json", "--body", output.name,
            "--if-none-match", "*")


def lock_coordinator(guard, wait_seconds):
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise OperationError("coordinator_busy") from None
            time.sleep(2)


def current_release():
    current = (RUNTIME / "current").resolve(strict=True)
    if current.parent != (RUNTIME / "releases").resolve() or not current.is_dir():
        raise OperationError("unknown_current_release")
    return current


def unpack_runtime(archive, destination):
    total = 0
    with tarfile.open(archive, mode="r:gz") as source:
        for member in source:
            name = PurePosixPath(member.name)
            if (str(name) != member.name or name.is_absolute() or ".." in name.parts
                    or not name.parts or not (member.isfile() or member.isdir())
                    or (name.parts[0] not in SOURCE_DIRECTORIES and member.name not in MANIFESTS)):
                raise OperationError("invalid_archive_member")
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            total += member.size
            if total > MAX_EXPANDED:
                raise OperationError("archive_too_large")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with source.extractfile(member) as contents, target.open("xb") as output:
                shutil.copyfileobj(contents, output)
            target.chmod(0o700 if member.mode & 0o111 else 0o600)


def install_runtime(bucket, digest):
    releases = RUNTIME / "releases"
    with (RUNS / "batch.lock").open("ab") as guard, \
            tempfile.TemporaryDirectory(prefix=".training-release-", dir=releases) as directory:
        lock_coordinator(guard, 120)
        current = current_release()
        release = releases / digest
        if current == release:
            return
        work = Path(directory)
        if release.exists():
            if release.resolve() != release or (release / ".training-archive-sha256").read_text() != digest:
                raise OperationError("unrecognized_staged_release")
            next_link = work / "current"
            next_link.symlink_to(release, target_is_directory=True)
            next_link.replace(RUNTIME / "current")
            return
        incoming = work / "release.tar.gz"
        aws("s3api", "get-object", "--bucket", bucket,
            "--key", f"runtime/archives/{digest}.tar.gz",
            "--range", f"bytes=0-{MAX_ARCHIVE}", str(incoming))
        if incoming.stat().st_size > MAX_ARCHIVE or hashlib.sha256(incoming.read_bytes()).hexdigest() != digest:
            raise OperationError("archive_digest_mismatch")
        unpacked = work / "source"
        unpacked.mkdir()
        unpack_runtime(incoming, unpacked)
        if any((unpacked / file).read_bytes() != (current / file).read_bytes() for file in MANIFESTS):
            raise OperationError("runtime_dependencies_changed")
        stage = work / "stage"
        stage.mkdir()
        for name in SOURCE_DIRECTORIES | MANIFESTS:
            (unpacked / name).rename(stage / name)
        for name in RETAINED_DIRECTORIES:
            existing = (current / name).resolve(strict=True)
            if existing.name != name or existing.parent.parent != releases.resolve() or not existing.is_dir():
                raise OperationError("unexpected_retained_directory")
            (stage / name).symlink_to(existing, target_is_directory=True)
        for file in ("scripts/run-jumpserve-synthetic-batch.mjs", "scripts/lib/jumpserve-synthetic-ec2.mjs"):
            subprocess.run(["node", "--check", str(stage / file)], timeout=15, check=True, capture_output=True)
        runner = stage / "scripts/run-jumpserve-training-batch.py"
        compile(runner.read_bytes(), runner.name, "exec")
        (stage / ".training-archive-sha256").write_text(digest)
        stage.rename(release)
        next_link = work / "current"
        next_link.symlink_to(release, target_is_directory=True)
        next_link.replace(RUNTIME / "current")


def read_state(path):
    with path.open("rb") as source:
        contents = source.read(262_145)
    if len(contents) > 262_144:
        raise OperationError("journal_too_large")
    return json.loads(contents)


def lease_directory(root, case, stage):
    paper = require(case["paper_id"], r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
    path = root / paper / f"ec2-{stage}" / "aws-lease"
    if path.resolve() != path:
        raise OperationError("unexpected_lease_path")
    return path


def checked_lease(directory, case):
    path = directory / "state.json"
    if path.is_symlink():
        raise OperationError("unexpected_lease_path")
    state = read_state(path)
    if (state.get("profile") != "jumpserve-experiment"
            or state.get("assessment_id") != case.get("database", {}).get("assessment_id")
            or not state.get("stacks") or any(s.get("region") != "us-east-1" for s in state["stacks"])):
        raise OperationError("lease_identity_mismatch")
    return state


def inspect_batch(root, journal):
    leases = []
    paper_errors = []
    for case in journal["cases"]:
        status = case.get("status")
        if status in {"generation_error", "verification_error"}:
            reason = str(case.get(status, "")).lower()
            code = next((label for label, match in PAPER_ERROR_CODES if match in reason), "unclassified")
            paper_errors.append({"paper": require(case["paper_id"], r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}"),
                                 "stage": "generator" if status == "generation_error" else "verifier", "code": code})
        for stage in ("generator", "verifier"):
            directory = lease_directory(root, case, stage)
            if not (directory / "state.json").is_file():
                continue
            state = checked_lease(directory, case)
            clean = all(stack.get("cleaned") is True for stack in state["stacks"])
            uncertain = any(stack.get("create_attempted") and not stack.get("id") for stack in state["stacks"])
            leases.append({"paper": case["paper_id"], "stage": stage, "cleaned": clean,
                           "creationUnconfirmed": not clean and uncertain})
    stop = journal.get("stop", {})
    reason = stop.get("reason", "")
    phase = stop.get("phase")
    status = journal["status"]
    return {"batchStatus": status if status in TERMINAL | {"running", "preparing"} else "unknown",
            "leases": leases,
            "paperErrors": paper_errors,
            "stopPhase": phase if phase in {"generating", "verifying", "saving_generator", "saving_verifier"} else None,
            "awsError": next((code for code in AWS_ERRORS if code in reason), None)}


def recover_stage(root, journal, paper, stage):
    if journal["status"] not in TERMINAL:
        raise OperationError("batch_active")
    match = next((case for case in journal["cases"] if case["paper_id"] == paper), None)
    if match is None:
        raise OperationError("paper_not_found")
    directory = lease_directory(root, match, stage)
    checked_lease(directory, match)
    script = current_release() / "skills/jumpserve-paper-assessment/scripts/aws_testbed.py"
    result = subprocess.run([sys.executable, "-B", str(script), "cleanup", "--lease", str(directory)],
                            timeout=920, capture_output=True)
    if result.returncode or not all(s.get("cleaned") is True for s in checked_lease(directory, match)["stacks"]):
        raise OperationError("worker_cleanup_unconfirmed")


def main():
    bucket, action, request, *arguments = sys.argv[1:]
    require(bucket, r"[a-z0-9-]{3,63}")
    record = {"requestId": require(request, r"[a-f0-9-]{1,40}")}
    if action == "release":
        digest, revision = arguments
        record.update(sha256=require(digest, r"[a-f0-9]{64}"), revision=require(revision, r"[a-f0-9]{40}"))
        key = f"runtime/receipts/{request}.json"
    else:
        batch, mode, paper, stage = arguments
        require(batch, r"[1-9][0-9]{0,9}")
        require(mode, r"inspect|recover")
        require(stage, r"generator|verifier")
        require(paper, r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
        if int(batch) > 2_147_483_647:
            raise OperationError("invalid_request")
        record.update(batchId=int(batch), mode=mode)
        key = f"diagnostics/{batch}/{request}.json"
    try:
        if action == "release":
            install_runtime(bucket, digest)
        else:
            root = RUNS / batch
            if root.resolve() != root or (root / "batch.json").is_symlink():
                raise OperationError("unexpected_journal_path")
            if mode == "recover":
                with (RUNS / "batch.lock").open("ab") as guard:
                    lock_coordinator(guard, 0)
                    recover_stage(root, read_state(root / "batch.json"), paper, stage)
            record.update(inspect_batch(root, read_state(root / "batch.json")))
        record["status"] = "ok"
    except OperationError as error:
        record.update(status="failed", reason=str(error))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError):
        record.update(status="failed", reason="operation_failed")
    receipt(bucket, key, record)
    return record["status"] != "ok"


if __name__ == "__main__":
    os.umask(0o077)
    try:
        sys.exit(main())
    except (OperationError, OSError, ValueError, subprocess.SubprocessError):
        sys.exit("Could not complete the fixed JumpServe training operation.")
