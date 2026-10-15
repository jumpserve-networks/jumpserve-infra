"""Package fixed local development evidence; no network, model or DB writes."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT.parent / 'jumpserve-front-end'

def digest(raw): return hashlib.sha256(raw).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-review', action='store_true', help='Archive the v9-v11 source correction separately; preserve the original interview bundle.')
    source_review = parser.parse_args().source_review
    versions = {'research-ideas-v'+str(n) for n in (range(9, 12) if source_review else range(3, 9))}
    files = {}
    def add_tree(directory, prefix):
        for path in sorted(directory.rglob('*')):
            # Raw failure diagnostics may contain account/provider details. Their
            # hashes and bounded classifications remain in the public reports.
            if path.is_file() and not (source_review and path.name.endswith('-provider-error.bin')):
                files[prefix+'/'+str(path.relative_to(directory))] = path.read_bytes()
    reports = ROOT/'.test-artifacts/research-ideas/evaluations'
    for path in sorted(reports.glob('*/evaluation-report.json')):
        report = json.loads(path.read_text())
        if report.get('prompt_version') in versions:
            add_tree(path.parent, 'evaluations/'+path.parent.name)
    for root, pattern, prefix in (
        (FRONT, '.test-artifacts/idea-interview/browser/*/validation-report.json', 'interview-browser'),
        (FRONT, '.test-artifacts/idea-guide/browser/*/validation-report.json', 'guided-browser'),
        (FRONT, '.test-artifacts/idea-review-sources/browser/*/validation-report.json', 'source-browser'),
        (ROOT, '.test-artifacts/research-ideas/database/*/validation-report.json', 'database'),
    ):
        for path in sorted(root.glob(pattern)):
            # Retain this feature's declared campaigns, including failed runs.
            data = json.loads(path.read_text())
            if source_review and data.get('started_at', '') < '2026-10-15T03:00': continue
            if not source_review and prefix == 'source-browser': continue
            if prefix == 'database' and not any('interview publication' in c['name'] for c in data.get('checks', [])): continue
            if prefix == 'guided-browser' and path.parent.name < '2026-10-14T23-45': continue
            if prefix == 'database': files[prefix+'/'+path.parent.name+'/validation-report.json'] = path.read_bytes()
            else: add_tree(path.parent, prefix+'/'+path.parent.name)
    for pattern in ('docs/idea-interview*.md', 'database/*idea_interview*.sql', 'database/seed-research-ideas-prompt-v[3-8].json', 'test/idea-interview-evaluation-cases-v1*.json'):
        for path in sorted(ROOT.glob(pattern)): files['source/infra/'+str(path.relative_to(ROOT))] = path.read_bytes()
    for name in ('agent/idea_interview.py','agent/research_ideas.py','agent/handler.py','test/agent_ideas_test.py','test/agent_interview_test.py','test/archive_idea_interview_evidence.py','test/evaluate_research_ideas.py','test/serve_research_ideas_fixture.py','test/check_research_ideas_database.py'):
        files['source/infra/'+name] = (ROOT/name).read_bytes()
    for name in ('app/components/research-workflow/idea-guide.tsx','app/components/research-workflow/idea-conversation.tsx','lib/idea-interview.ts','lib/research-idea-api.ts','scripts/research-ideas-interview-cases.mjs','scripts/research-ideas-guided-cases.mjs','scripts/verify-research-ideas.mjs','tests/idea-interview.test.mjs','tests/research-idea-api.test.mjs'):
        files['source/frontend/'+name] = (FRONT/name).read_bytes()
    if source_review:
        for pattern in ('docs/idea-review-source-fidelity*.md', 'database/*idea_review_sources*.sql', 'database/seed-research-ideas-prompt-v9.json', 'database/seed-research-ideas-prompt-v1[01].json', 'test/idea-review-source-cases-v1*.json'):
            for path in sorted(ROOT.glob(pattern)): files['source/infra/'+str(path.relative_to(ROOT))] = path.read_bytes()
        for name in ('agent/idea_review.py', 'test/agent_review_sources_test.py', 'docs/idea-interview-validation-v1.json'):
            files['source/infra/'+name] = (ROOT/name).read_bytes()
        for name in ('app/components/research-workflow/idea-review-sources.tsx', 'app/components/research-workflow/idea-workspace.tsx', 'lib/idea-review-sources.ts', 'tests/idea-review-sources.test.mjs', 'scripts/research-ideas-source-cases.mjs'):
            files['source/frontend/'+name] = (FRONT/name).read_bytes()
        original = ROOT/'docs/idea-interview-evidence-v1.tar.gz'
        previous = json.loads((ROOT/'docs/idea-interview-validation-v1.json').read_text())
        assert digest(original.read_bytes()) == previous['evidence_bundle']['sha256'], 'Historical evidence bundle changed'
        files['historical-evidence.json'] = (json.dumps(previous['evidence_bundle'], indent=2)+'\n').encode()
    log_version = 'idea-review' if source_review else 'idea-interview'
    for root, names, prefix in ((ROOT, [log_version+'-agent.log',log_version+'-database.log'], 'infra'), (FRONT, [log_version+'-tests.log',log_version+'-lint.log'], 'frontend')):
        for name in names: files['logs/'+prefix+'/'+name] = (root/'.test-artifacts'/name).read_bytes()
    build = Path('/private/tmp/jumpserve-guided-release-20261014/jumpserve-front-end/.test-artifacts')/(log_version+'-build.log')
    files['logs/frontend/build.log'] = build.read_bytes()
    manifest = [dict(path=name, sha256=digest(raw), bytes=len(raw)) for name, raw in sorted(files.items())]
    files['manifest.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    destination = ROOT/'docs'/('idea-review-source-fidelity-evidence-v1.tar.gz' if source_review else 'idea-interview-evidence-v1.tar.gz')
    with destination.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as zipped, tarfile.open(fileobj=zipped, mode='w') as archive:
        for name, raw in sorted(files.items()):
            info = tarfile.TarInfo(name); info.size = len(raw); info.mode = 0o644
            archive.addfile(info, io.BytesIO(raw))
    with tarfile.open(destination, 'r:gz') as archive:
        restored = json.load(archive.extractfile('manifest.json'))
        for item in restored:
            raw = archive.extractfile(item['path']).read()
            assert len(raw) == item['bytes'] and digest(raw) == item['sha256'], item['path']
    print(json.dumps(dict(path=str(destination), sha256=digest(destination.read_bytes()), bytes=destination.stat().st_size,
        original_files=len(manifest), original_bytes=sum(item['bytes'] for item in manifest), retrieved_hashes_verified=True)))

if __name__ == '__main__': main()
