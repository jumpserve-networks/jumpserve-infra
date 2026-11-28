import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


BIN = Path(__file__).resolve().parents[1] / "bin"
OPS = runpy.run_path(str(BIN / "training-operations.py"))
TEMPLATE = runpy.run_path(str(BIN / "render-training-operations.py"))["template"]


class TrainingOperationsTests(unittest.TestCase):
    def test_roles_use_only_their_fixed_operations(self):
        resources = TEMPLATE()["Resources"]
        role = resources["GithubReleaseRole"]["Properties"]
        trust, = role["AssumeRolePolicyDocument"]["Statement"]
        self.assertEqual(trust["Condition"]["StringEquals"]["token.actions.githubusercontent.com:sub"],
                         "repo:jumpserve-networks/jumpserve-front-end:ref:refs/heads/main")
        release_policy = role["Policies"][0]["PolicyDocument"]["Statement"]
        local_policy = resources["LocalDiagnosticsAccess"]["Properties"]["PolicyDocument"]["Statement"]
        self.assertIn("${ReleaseDocument}", json.dumps(release_policy[0]))
        self.assertNotIn("DiagnosticsDocument", json.dumps(release_policy))
        self.assertIn("${DiagnosticsDocument}", json.dumps(local_policy[0]))
        self.assertNotIn("ReleaseDocument", json.dumps(local_policy))
        self.assertEqual(release_policy[2]["Condition"], {"Null": {"s3:if-none-match": "false"}})
        for name in ("ReleaseDocument", "DiagnosticsDocument"):
            document = resources[name]["Properties"]["Content"]
            self.assertTrue(all(p["interpolationType"] == "ENV_VAR" and p["allowedPattern"]
                                for p in document["parameters"].values()))

    def test_archive_rejects_escape_links_and_corpus_replacements(self):
        for name, kind in (("../outside", tarfile.REGTYPE), ("lib/link", tarfile.SYMTYPE),
                           ("answer-keys/benchmark.json", tarfile.REGTYPE)):
            with self.subTest(name=name), TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "archive.tar.gz"
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "/etc/passwd"
                with tarfile.open(archive, "w:gz") as target:
                    target.addfile(member, io.BytesIO())
                with self.assertRaisesRegex(OPS["OperationError"], "invalid_archive_member"):
                    OPS["unpack_runtime"](archive, root / "out")

    def test_diagnostics_redact_error_details_and_confirm_exact_lease(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lease = root / "Example" / "ec2-generator" / "aws-lease"
            lease.mkdir(parents=True)
            case = {"paper_id": "Example", "database": {"assessment_id": "fixture-lease"}}
            state = {"profile": "jumpserve-experiment", "assessment_id": "fixture-lease",
                     "stacks": [{"region": "us-east-1", "create_attempted": True}]}
            (lease / "state.json").write_text(json.dumps(state))
            journal = {"status": "stopped", "cases": [case],
                       "stop": {"phase": "generating", "reason": "ThrottlingException at /private/path"}}
            self.assertEqual(OPS["inspect_batch"](root, journal), {
                "batchStatus": "stopped", "stopPhase": "generating", "awsError": "ThrottlingException",
                "leases": [{"paper": "Example", "stage": "generator", "cleaned": False, "creationUnconfirmed": True}],
            })
            case["database"]["assessment_id"] = "other-lease"
            with self.assertRaisesRegex(OPS["OperationError"], "lease_identity_mismatch"):
                OPS["inspect_batch"](root, journal)

    def test_recovery_requires_a_terminal_batch(self):
        with self.assertRaisesRegex(OPS["OperationError"], "batch_active"):
            OPS["recover_stage"](Path("/unavailable"), {"status": "running"}, "Example", "generator")

    def test_release_reuses_approved_inputs_and_leaves_previous_release_available(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            runtime, runs = root / "runtime", root / "runs"
            old = runtime / "releases" / "baseline"
            for name in OPS["RETAINED_DIRECTORIES"]:
                (old / name).mkdir(parents=True)
            runs.mkdir()
            (runtime / "current").symlink_to(old)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                for name in OPS["SOURCE_DIRECTORIES"]:
                    entry = tarfile.TarInfo(name)
                    entry.type = tarfile.DIRTYPE
                    output.addfile(entry)
                for name in (*OPS["MANIFESTS"], "scripts/run-jumpserve-synthetic-batch.mjs",
                             "scripts/lib/jumpserve-synthetic-ec2.mjs", "scripts/run-jumpserve-training-batch.py"):
                    value = b"{}" if name in OPS["MANIFESTS"] else b""
                    entry = tarfile.TarInfo(name)
                    entry.size = len(value)
                    output.addfile(entry, io.BytesIO(value))
                    if name in OPS["MANIFESTS"]:
                        (old / name).write_bytes(value)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.dict(OPS["install_runtime"].__globals__, {
                "RUNTIME": runtime, "RUNS": runs, "aws": lambda *args: shutil.copyfile(archive, args[-1]),
            }):
                OPS["install_runtime"]("fixture-bucket", digest)
                OPS["install_runtime"]("fixture-bucket", digest)
            active = (runtime / "current").resolve()
            self.assertEqual(active.name, digest)
            for name in OPS["RETAINED_DIRECTORIES"]:
                self.assertEqual((active / name).resolve(), old / name)
            self.assertTrue(old.is_dir())
