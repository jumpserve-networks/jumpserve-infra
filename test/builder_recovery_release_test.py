"""Storage retries must reconcile one original archive, never replace it."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_release_under_test', ROOT / 'bin/builder-recovery-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class OriginalArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root / 'artifacts'
        self.source = self.base / 'frozen'
        self.out = self.base / 'attempt'
        self.source.mkdir(parents=True)
        self.out.mkdir()
        (self.root / 'docs').mkdir()
        (self.source / 'frozen.json').write_text('{"prompts":[]}')
        buffer = io.BytesIO()
        payload = b'original raw bytes\x00\xff'
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('original.bin', payload)
            archive.writestr('artifact-manifest.json', json.dumps([dict(path='original.bin', sha256=hashlib.sha256(payload).hexdigest())]))
        self.raw = buffer.getvalue()
        self.archive = self.source / 'original.zip'
        self.archive.write_bytes(self.raw)
        self.pending = dict(archive='artifacts/frozen/original.zip', sha256=hashlib.sha256(self.raw).hexdigest(), members=1, value=dict(status='deployed-with-conditional-verification-gaps'))
        self.requests = []

    def run_finish(self, responses):
        iterator = iter(responses)

        def open_request(request, *, timeout):
            self.requests.append(request)
            self.assertEqual(timeout, 180)
            value = next(iterator)
            if isinstance(value, Exception):
                raise value
            return io.BytesIO(value)

        with patch.object(release, 'ROOT', self.root), patch.object(release, 'BASE', self.base), patch.object(release.r, 'aws', return_value={'SecretString': 'TEST-ONLY-NOT-A-CREDENTIAL'}), patch.object(release.r.prior.guard.OPEN, 'open', side_effect=open_request):
            return release.finish_release(self.source, self.out, self.pending)

    def test_existing_matching_object_is_not_uploaded_again(self):
        result = self.run_finish([self.raw])
        self.assertEqual([r.get_method() for r in self.requests], ['GET'])
        self.assertEqual(result['evidence']['sha256'], self.pending['sha256'])
        self.assertEqual(self.archive.read_bytes(), self.raw)

    def test_uncertain_write_is_reconciled_by_exact_get(self):
        missing = urllib.error.HTTPError('https://example.invalid', 400, 'missing', {}, io.BytesIO(b'{"error":"not_found"}'))
        result = self.run_finish([missing, urllib.error.URLError('lost upload acknowledgement'), self.raw])
        self.assertEqual([r.get_method() for r in self.requests], ['GET', 'POST', 'GET'])
        self.assertEqual(len({r.full_url for r in self.requests}), 1)
        self.assertEqual(self.requests[1].data, self.raw)
        self.assertEqual(dict((k.lower(), v) for k, v in self.requests[1].header_items())['x-upsert'], 'false')
        self.assertEqual(result['evidence']['retrieved_sha256'], self.pending['sha256'])
        self.assertTrue((self.out / 'archive-write-unconfirmed.json').exists())

    def test_conflicting_existing_object_is_never_overwritten(self):
        with self.assertRaisesRegex(AssertionError, 'unconfirmed'):
            self.run_finish([b'conflicting remote bytes'])
        self.assertEqual([r.get_method() for r in self.requests], ['GET'])
        self.assertEqual(self.archive.read_bytes(), self.raw)

    def test_unavailable_initial_read_does_not_blindly_write(self):
        with self.assertRaises(urllib.error.URLError):
            self.run_finish([urllib.error.URLError('connection reset')])
        self.assertEqual([r.get_method() for r in self.requests], ['GET'])
        self.assertEqual(self.archive.read_bytes(), self.raw)


if __name__ == '__main__':
    unittest.main()
