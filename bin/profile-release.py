"""Fixed JumpServe profile migration/release verification; no arbitrary inputs."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('profile_guard', ROOT / 'bin/openclaw-release.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
MIGRATION = ROOT / 'database/202610230001_user_profiles.sql'
EXPECTED = '24eaa3441a6636474ea462634618efc62fa0730ea92224879cf4359221e6c9ac'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def inspect():
    return dict(
        columns=r.admin.query("select column_name,data_type,is_nullable from information_schema.columns where table_schema='public' and table_name='profiles' order by ordinal_position"),
        query_context=r.admin.query("select current_user reader,current_setting('search_path') search_path,has_function_privilege(current_user,to_regprocedure('public.profile_timezone_valid(text)'),'EXECUTE') reader_execute,has_function_privilege('authenticated',to_regprocedure('public.profile_timezone_valid(text)'),'EXECUTE') browser_execute"),
        table=r.admin.query("select relrowsecurity from pg_class where oid=to_regclass('public.profiles')"),
        policies=r.admin.query("select policyname,permissive,to_json(roles) roles,cmd,qual,with_check from pg_policies where schemaname='public' and tablename='profiles' order by policyname"),
        constraints=r.admin.query("select contype,pg_get_constraintdef(oid) definition from pg_constraint where conrelid=to_regclass('public.profiles') order by conname"),
        function=r.admin.query("select p.provolatile,p.prosecdef,p.proconfig,pg_get_functiondef(p.oid) definition from pg_proc p where p.oid=to_regprocedure('public.profile_timezone_valid(text)')"))


def verify():
    data = inspect()
    require(data['columns'] == [dict(column_name=n, data_type=t, is_nullable=z) for n,t,z in [('id','uuid','NO'),('first_name','text','NO'),('last_name','text','NO'),('timezone','text','YES')]], 'Profile columns differ.')
    require(data['table'] == [dict(relrowsecurity=True)], 'Profile RLS is not enabled.')
    expected = dict(profile_owner_read='SELECT', profile_owner_insert='INSERT', profile_owner_update='UPDATE')
    owner = [p for p in data['policies'] if p['policyname'] in expected]
    require(len(owner) == 3, 'Profile owner policies are missing.')
    for p in owner:
        require(p['cmd'] == expected[p['policyname']] and p['roles'] == ['authenticated'] and p['permissive'] == 'PERMISSIVE', 'Unexpected profile policy role/command.')
        for key in (['with_check'] if p['cmd'] == 'INSERT' else ['qual'] if p['cmd'] == 'SELECT' else ['qual','with_check']):
            require(''.join(p[key].split()) == '((SELECTauth.uid()ASuid)=id)', 'Owner policy expression differs.')
    additional = [p for p in data['policies'] if p['policyname'] not in expected]
    signed_in = "(((SELECTauth.uid()ASuid)ISNOTNULL)AND((SELECT(auth.jwt()->>'is_anonymous'::text))ISDISTINCTFROM'true'::text))"
    require(len(additional) == 1, 'Expected the existing global signed-in-user safety policy.')
    restriction = additional[0]
    require(restriction['policyname'] == 'jumpserve_require_signed_in_user' and restriction['roles'] == ['anon','authenticated'] and restriction['cmd'] == 'ALL' and restriction['permissive'] == 'RESTRICTIVE', 'Global signed-in-user policy differs.')
    require(all(''.join(restriction[key].split()) == signed_in for key in ('qual','with_check')), 'Global signed-in-user predicate differs.')
    definitions = ' '.join(c['definition'] for c in data['constraints'])
    require(len(data['constraints']) == 5 and 'FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE' in definitions and 'PRIMARY KEY (id)' in definitions and 'profile_timezone_valid(timezone)' in definitions, 'Profile constraints differ.')
    require(len(data['function']) == 1 and data['function'][0]['provolatile'] == 's' and not data['function'][0]['prosecdef'] and data['function'][0]['proconfig'] == ['search_path=""'], 'Timezone validator security differs.')
    # Management API's supabase_read_only_user cannot execute this deliberately
    # private function. Use the authorized connection for this fixed SELECT only;
    # the pinned STABLE SQL body reads pg_timezone_names and writes no records.
    checks = r.admin.query("select public.profile_timezone_valid('America/New_York') ny,public.profile_timezone_valid('Asia/Tokyo') tokyo,public.profile_timezone_valid('UTC') utc,public.profile_timezone_valid(null) missing,public.profile_timezone_valid('invalid/zone') invalid,public.profile_timezone_valid('') blank", read_only=False)
    require(checks == [dict(ny=True,tokyo=True,utc=True,missing=True,invalid=False,blank=False)], 'Timezone validator behavior differs.')
    grants = r.admin.query("select role,has_any_column_privilege(role,'public.profiles','SELECT') can_read,has_any_column_privilege(role,'public.profiles','INSERT') can_insert,has_any_column_privilege(role,'public.profiles','UPDATE') can_update,has_table_privilege(role,'public.profiles','DELETE') can_delete from (values ('anon'),('authenticated')) x(role) order by role")
    require(grants == [dict(role='anon',can_read=False,can_insert=False,can_update=False,can_delete=False),dict(role='authenticated',can_read=True,can_insert=True,can_update=True,can_delete=False)], 'Profile grants differ.')
    data.update(grants=grants, timezone_checks=checks, validator_probe='Fixed SELECT through the authorized Management connection; no data writes. The read-only management role has no EXECUTE grant.')
    config=json.loads((ROOT/'cdk.json').read_bytes())['context']
    request=urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/rest/v1/profiles?select=id&limit=1',headers={'apikey':config['supabaseAnonKey'],'Authorization':'Bearer '+config['supabaseAnonKey']})
    try:
        with r.prior.guard.OPEN.open(request,timeout=25) as response:
            status=response.status
    except urllib.error.HTTPError as error:
        status=error.code
    require(status in (401,403), 'Anonymous profile HTTP read was not denied.')
    data['anonymous_profile_http_status']=status
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inspect','apply','verify','frontend-status'])
    args=parser.parse_args()
    directory=ROOT/'.test-artifacts/profile-release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    report=dict(protocol='profile-production-release-v1',mode=args.mode,status='running',started_at=dt.datetime.now(dt.timezone.utc).isoformat(),measured_charges_usd=None)
    try:
        raw=MIGRATION.read_bytes()
        require(sha(raw)==EXPECTED,'Unexpected migration bytes.')
        report['migration_sha256']=sha(raw)
        report['targets']=r.target()
        before=r.prior.pointers()
        if args.mode=='inspect': report['inspection']=inspect()
        elif args.mode in ('apply','verify'):
            existing=inspect()
            if args.mode=='apply' and not existing['columns']:
                require(not existing['function'] and not existing['table'],'Unexpected partially existing profile schema.')
                (directory/'migration-original.sql').write_bytes(raw)
                report['migration_submission_started']=True
                (directory/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
                r.admin.query(raw.decode(),read_only=False)
                report['migration_applied']=True
            else: report['migration_applied']=False
            report['verification']=verify()
        else: report['jobs']=r.aws('amplify','list-jobs','--app-id','d24jvguj7brnkj','--branch-name','main','--max-results','3')['jobSummaries']
        require(r.prior.pointers()==before,'Active prompt settings changed during this release operation.')
        report['active_prompt_settings_preserved']=True
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',reason=str(error))
        raise
    finally:
        report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        (directory/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(directory=str(directory),**report),indent=2))


if __name__=='__main__': main()
