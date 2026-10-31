"""Assessment failure -> private outbox -> priority platform queue SQL checks.

Called by check_platform_database.py in its retained loopback-only fixture.
No provider, cloud, remote database or experiment calls are made.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
import uuid


def run(fixtures, work, control, policy):
    f=SimpleNamespace(**fixtures)
    q=f.quote
    def uid():return str(uuid.uuid4())
    def count(table, where='true'):
        return int(f.sql('select count(*) from public.'+table+' where '+where))
    def expect(condition):
        if not condition:raise AssertionError('Assessment blocker invariant failed.')
    def workflow(status='running', seconds=86400, budget=None):
        ident=uid()
        f.sql('insert into public.research_autonomy_workflows(study_id,status,deadline_at,max_spend_cents) values('+q(ident)+','+q(status)+",clock_timestamp()+make_interval(secs=>"+str(seconds)+'),'+('null' if budget is None else str(budget))+')')
        return ident
    def task(study, status='queued', reason='Synthetic task', stage='planning'):
        ident=uid()
        f.sql('insert into public.research_autonomy_tasks(id,study_id,stage,status,reason) values('+','.join(map(q,[ident,study,stage,status,reason]))+')')
        return ident
    def reason_update(task_id, reason, status='blocked'):
        f.sql('update public.research_autonomy_tasks set status='+q(status)+',reason='+q(reason)+' where id='+q(task_id))
    def admitted(task_id):
        return json.loads(f.sql('select coalesce(jsonb_agg(to_jsonb(t)),\'[]\') from public.platform_tasks t join public.platform_assessment_repair_links l on l.platform_task_id=t.id join public.platform_assessment_blockers b on b.id=l.blocker_id where b.assessment_task_id='+q(task_id)))
    def drain():return work('maintenance',payload=dict(policy_sha256=policy))
    def cancel_repairs():
        for ident in json.loads(f.sql("select coalesce(jsonb_agg(id),'[]') from public.platform_tasks where status='queued'")):
            control('cancel',ident)

    # Minimal shapes of the actual research relations used by the adapter. The
    # original platform fixture above has already exercised its dispatch wrapper.
    f.sql("""create table public.research_autonomy_workflows(
 study_id uuid primary key,status text not null,deadline_at timestamptz not null,
 max_spend_cents integer,committed_cents integer not null default 500);
create table public.research_autonomy_tasks(
 id uuid primary key,study_id uuid not null references public.research_autonomy_workflows(study_id),
 stage text not null,status text not null,reason text not null,context jsonb not null default '{}',
 lease_until timestamptz,unique(study_id,id));
create table public.research_autonomy_repairs(
 id uuid primary key,task_id uuid not null references public.research_autonomy_tasks(id),state text not null,reason text not null);
alter table public.research_model_dispatches add column task_id uuid references public.research_autonomy_tasks(id);
alter table public.research_model_dispatches add column provenance jsonb not null default '{}';
""")
    original=workflow()
    existing=task(original,'blocked','ValueError: UUID required')
    cancelled=workflow('cancelled')
    inactive=task(cancelled,'blocked','Cancelled assessment failure')
    def retained_functions():
        return json.loads(f.sql("select jsonb_object_agg(proname,prosrc) from pg_proc where pronamespace='public'::regnamespace and proname in ('platform_worker','platform_control','research_model_dispatch','research_model_dispatch_before_platform_v1')"))
    original_functions=retained_functions()
    f.sql((f.ROOT/'database/202610310002_assessment_blocker_repairs.sql').read_text())
    def guards_preserved():
        current=retained_functions()
        for name in ('platform_control','research_model_dispatch','research_model_dispatch_before_platform_v1'):
            expect(current[name]==original_functions[name])
        expect(json.loads(f.sql("select to_json(prosrc) from pg_proc where oid='public.platform_worker_before_assessment_v1(text,uuid,uuid,uuid,jsonb)'::regprocedure"))==original_functions['platform_worker'])
    f.check('adapter retains original task admission release and research host guards unchanged',guards_preserved)
    f.check('activation captures existing active blockers and excludes cancelled assessments',lambda: expect(count('platform_assessment_blockers')==1 and count('platform_assessment_blockers','assessment_task_id='+q(inactive))==0))
    f.check('blocker adapter cannot bypass worker policy authorization',lambda: work('maintenance',payload=dict(policy_sha256='b'*64),fail=True))
    control('pause')
    f.check('pause retains blocker observation without admitting repair work',lambda: expect(drain() is None and not admitted(existing)))
    control('resume')
    first=drain()
    f.check('assessment repair bypasses the already consumed daily maintenance slot',lambda: expect(len(first['assessment_repair_tasks'])==1 and len(admitted(existing))==1))
    repair=admitted(existing)[0]
    f.check('urgent repair retains fixed task limits and original assessment identity',lambda: expect(repair['priority']==0 and repair['max_reserved_cents']==10000 and existing in repair['objective'] and original in repair['objective'] and 'UUID required' in repair['objective']))
    f.check('new records use the existing private dashboard event stream',lambda: expect(count('platform_events',"kind='assessment-blocker-detected'")==1 and count('platform_events',"kind='assessment-repair-queued'")==1))

    def deduplication():
        reason_update(existing,'ValueError: UUID required')
        reason_update(existing,'ValueError: UUID required')
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:drain(),range(2)))
        expect(len(admitted(existing))==1)
        control('cancel',repair['id'])
        reason_update(existing,'ValueError: UUID required')
        drain()
        expect(len(admitted(existing))==1 and admitted(existing)[0]['cancel_requested'])
    f.check('duplicate reports and concurrent workers cannot reset a cancelled incident budget',deduplication)

    active=workflow()
    new_task=task(active)
    before=count('platform_assessment_blockers')
    reason_update(new_task,'Original lease expired: '+uid())
    reason_update(new_task,'Original lease expired: '+uid())
    f.check('changing transport identities cannot multiply the same blocker',lambda: expect(count('platform_assessment_blockers')==before+1))
    other=task(active)
    repair_id=uid()
    f.sql('insert into public.research_autonomy_repairs values('+','.join(map(q,[repair_id,other,'waiting','An original native call is unresolved; no replacement admitted.']))+')')
    dispatch_task=task(active)
    f.sql('insert into public.research_model_dispatches(id,status,task_id,provenance) values('+q(uid())+",'unknown',"+q(dispatch_task)+','+f.js(dict(reason='Original provider outcome is unconfirmed.'))+')')
    f.check('waiting repairs and uncertain dispatches trigger platform triage',lambda: expect(count('platform_assessment_blockers','assessment_task_id in ('+q(other)+','+q(dispatch_task)+')')==2))

    def rollback():
        before=count('platform_assessment_blockers')
        f.sql('begin; update public.research_autonomy_tasks set status=\'blocked\',reason=\'Rolled back fixture\' where id='+q(dispatch_task)+'; rollback')
        expect(count('platform_assessment_blockers')==before)
    f.check('rolled-back research failures cannot leave phantom repair tasks',rollback)

    def exclusions():
        initial=count('platform_assessment_blockers')
        for status in ('cancelled','budget','deadline','completed'):
            task(workflow(status),'blocked','Terminal workflow fixture')
        task(workflow(seconds=-1),'blocked','Expired workflow fixture')
        exhausted=workflow(budget=500)
        task(exhausted,'blocked','Exhausted assessment fixture')
        task(active,'waiting','Normal experiment waiting')
        expect(count('platform_assessment_blockers')==initial)
    f.check('ordinary waiting and stopped or exhausted assessments do not create new repair authority',exclusions)

    def redact():
        sensitive='UUID required; Bearer secret-token; password="private password"; user@example.invalid; https://example.invalid/private; /Users/example/private/file; AKIAABCDEFGHIJKLMNOP; sk-longsecret12345; 192.0.2.12; arn:aws:s3:::private'
        safe=f.sql('select public.platform_assessment_diagnostic('+q(sensitive)+')')
        expect('UUID required' in safe)
        for forbidden in ('secret-token','private password','user@example.invalid','example.invalid','/Users/','AKIA','sk-longsecret','192.0.2.12','arn:aws:'):expect(forbidden not in safe)
        expect(len(f.sql('select public.platform_assessment_diagnostic('+q('x '*3000)+')'))<=2000)
        for text in ('prompt="private content"','-----BEGIN PRIVATE KEY----- confidential'):
            expect('omitted' in f.sql('select public.platform_assessment_diagnostic('+q(text)+')'))
    f.check('operational packets redact credentials and private locations with explicit size limits',redact)

    # Repair events are captured even while paused; admission waits for resume.
    control('pause')
    paused_task=task(active,'blocked','New failure recorded during owner pause')
    f.check('pause does not lose newly identified blockers',lambda: expect(count('platform_assessment_blockers','assessment_task_id='+q(paused_task))==1 and drain() is None))
    control('resume')
    drain()
    f.check('resume drains retained blocker signals without waiting a day',lambda: expect(len(admitted(paused_task))==1))

    # New repair tasks follow the unchanged research-first host boundary.
    research=uid()
    f.sql('insert into public.research_model_dispatches(id,status,task_id) values('+q(research)+",'running',"+q(new_task)+')')
    f.check('active research dispatch still fences platform native work',lambda: expect(work('claim',payload=dict(policy_sha256=policy)) is None))
    f.sql('delete from public.research_model_dispatches where id='+q(research))
    f.sql("update public.research_autonomy_tasks set status='running',lease_until=clock_timestamp()+interval '5 minutes' where id="+q(new_task))
    f.sql('insert into public.research_model_dispatches(id,status,task_id) values('+q(research)+",'queued',"+q(new_task)+')')
    f.check('already admitted valid research dispatches retain their host priority',lambda: expect(work('claim',payload=dict(policy_sha256=policy)) is None))
    f.sql('delete from public.research_model_dispatches where id='+q(research))
    claimed=work('claim',payload=dict(policy_sha256=policy))
    f.check('urgent repairs precede routine maintenance at the next safe host slot',lambda: expect(claimed['priority']==0))
    token=claimed['lease_token'];platform_id=claimed['id']
    parent=f.sql('select b.study_id from public.platform_assessment_repair_links l join public.platform_assessment_blockers b on b.id=l.blocker_id where l.platform_task_id='+q(platform_id))
    f.sql("update public.research_autonomy_workflows set status='cancelled' where study_id="+q(parent))
    f.check('assessment cancellation stops new repair calls while allowing receipt reconciliation',lambda: expect(work('lease',platform_id,token)['cancel_requested'] and work('begin-run',platform_id,token,{})['denied']=='assessment-stopped'))
    f.check('cancelled assessment cannot admit a new repair publication',lambda: work('begin-operation',platform_id,token,dict(id=uid(),kind='publish',request_sha256='e'*64,request={}),fail=True))
    work('checkpoint',platform_id,token,dict(status='cancelled',reason='Synthetic parent cancellation honored.'))
    cancel_repairs()

    def security():
        work('heartbeat',payload=dict(status='ready'),role='authenticated',fail=True)
        for relation in ('platform_assessment_repair_policy','platform_assessment_blockers','platform_assessment_repair_links'):
            expect(f.sql("select relrowsecurity from pg_class where oid="+q('public.'+relation)+'::regclass')=='t')
            for role in ('anon','authenticated'):
                f.sql('select * from public.'+relation,role=role,fail=True)
            f.sql('delete from public.'+relation,role='service_role',fail=True)
        for role in ('anon','authenticated','service_role'):
            f.sql('select public.platform_capture_assessment_blocker(\'task\','+q(existing)+','+q(existing)+",'blocked','forged')",role=role,fail=True)
            f.sql('select public.platform_worker_before_assessment_v1(\'maintenance\','+q(uid())+')',role=role,fail=True)
        f.sql("update public.platform_assessment_blockers set diagnostic='rewritten'",fail=True)
        f.sql("update public.platform_assessment_repair_policy set source_instruction='rewritten'",fail=True)
    f.check('blocker history and authority remain private immutable and unforgeable by runtime roles',security)
