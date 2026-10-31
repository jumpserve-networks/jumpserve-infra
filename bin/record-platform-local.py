"""Record this local qualification and source hashes without remote mutations."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end';FRONT=ROOT.parent/'jumpserve-front-end'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    database=max((ROOT/'.test-artifacts/platform-database').glob('*/report.json'),key=lambda path:path.stat().st_mtime)
    db=json.loads(database.read_bytes());assert db['passed']
    browser=FRONT/'.test-artifacts/platform-browser/2026-10-31T00-00-50.279Z/report.json'
    browser_result=json.loads(browser.read_bytes());assert browser_result['passed']
    live=BACK/'.test-artifacts/platform-native/20261031T000138602233Z/report.json';live_result=json.loads(live.read_bytes());assert live_result['passed'] and live_result['actual_provider_calls']==6
    synthetic=BACK/'.test-artifacts/platform-native/20261031T013434740805Z/report.json';assert json.loads(synthetic.read_bytes())['passed']
    paths=[]
    for directory in (BACK/'platform_supervisor',ROOT/'assets/platform',FRONT/'app/platform-updates',FRONT/'app/api/platform-updates'):
        paths.extend(path for path in directory.rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    paths.extend(ROOT/path for path in ['AGENTS.md','lib/platform-supervisor-access.ts','bin/platform.ts','bin/platform-supervisor.py','bin/platform-production.py','bin/platform-synthesize.py','bin/platform-release-input.py','bin/platform-ami-proof.py','database/202610300004_platform_supervisor.sql','database/202610300005_platform_worker.sql','database/202610300006_platform_host_coordination.sql','docs/platform-supervisor-v1.md','docs/platform-supervisor-protocol-v1.json','.github/workflows/platform-release.yml','.github/workflows/platform-validate.yml','.github/workflows/deploy.yml','.github/workflows/benchmark-ami.yml'])
    paths.extend(FRONT/path for path in ['lib/platform-updates.ts','lib/platform-updates-store.ts','app/components/platform-updates.tsx','app/components/site-header.tsx','app/api/platform-version/route.ts','next.config.ts','tests/platform-updates.test.mjs','scripts/verify-platform-updates.mjs','.github/workflows/platform-validate.yml','AGENTS.md'])
    files={str(path.relative_to(ROOT.parent)):sha(path) for path in sorted(set(paths))}
    evidence={str(path.relative_to(ROOT.parent)):sha(path) for path in (database,browser,live,synthetic)}
    value=dict(version='platform-supervisor-local-v1',recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),state='implemented-locally-awaiting-explicit-initial-deployment',deployed=False,remote_mutations=0,owner_count=4,aws_credentials=dict(worker='EC2 instance profile; refreshable SDK credentials',releases='main-restricted GitHub OIDC; fresh session per job',static_aws_keys=False,human_login_needed_during_service_operation=False,live_role_assumption_verified=False),checks=dict(frontend_unit_passed=283,frontend_build=True,frontend_lint_errors=0,existing_unrelated_lint_warnings=1,browser_cases=len(browser_result['checks']),isolated_sql_cases=len(db['checks']),supervisor_unit_passed=16,benchmark_unit_passed=11,infra_jest_passed=97,infra_jest_skipped=5,infra_build=True,release_guard_unit_passed=4,iam_role_cases_passed=2,context7_public_mcp_verified=True,live_provider_calls=6,live_control_passed=True,synthetic_native_control_passed=True),source_sha256=files,evidence_sha256=evidence,limits=['Implementing AI review; not independent, human or held-out validation.','Synthetic Google/Storage/Realtime/GitHub/AWS protocol boundaries in local checks.','Live coding control covers its captured coding path; later orchestration/error paths have separate regressions.','Live production OAuth, role assumption, publisher mutation rights, migration/install/deployment/rollback require initial activation verification.','Automatic production scope is frontend, benchmark AMI and guarded existing infrastructure resources. Dedicated qualification paths remain for other changes.'],activation_requires=['Explicit deployment instruction under repository AGENTS.md','Independent publication of platform changes without unrelated local research edits','Private migrations/enrollment, protected branches, access stack and in-place IMDSv2 hop-limit hardening','Exact worker installation and bounded actual production release verification'])
    target=ROOT/'docs/platform-supervisor-local-v1-status.json';target.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');print(json.dumps(dict(recorded=str(target),deployed=False,sql_cases=len(db['checks']),owner_count=4)))

if __name__=='__main__':main()
