"""Private Slack task delegation and evidence, in a retained loopback database."""
import json
import uuid
import check_private_continuation_context_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION = '202611040001_platform_slack_gateway.sql'


def main():
    previous.main()
    raw = (f.ROOT / 'database' / MIGRATION).read_bytes()
    f.query(raw.decode()); f.report['migration_sha256'][MIGRATION] = workflow.digest(raw)
    q = f.sql_text
    team, channel, owner = 'TSLACK', 'CSLACK', 'UDMOWNER'
    delegated = f.query("select user_id from platform_operators where role='owner' limit 1")
    f.query('insert into platform_slack_bindings(team_id,channel_id,dm_owner,delegated_by) values(' + ','.join(map(q, (team, channel, owner, delegated))) + ')')

    def rpc(name, *values, role='service_role'):
        args = [f.sql_json(v) if isinstance(v, dict) else 'null' if v is None else q(v) for v in values]
        return json.loads(f.query('select public.' + name + '(' + ','.join(args) + ')', role=role))
    def status(sender='USECOND', room=channel): return rpc('platform_slack_status', team, room, sender)
    def request(ident=None, session=None, payload=None, sender='USECOND', room=channel):
        return rpc('platform_slack_request', ident or f.uid(), team, room, sender, session or f.uid(), payload or task)
    task = dict(title='Synthetic shared Slack request', objective='Local fixture only; no provider calls or production changes.',
                repositories=['jumpserve-networks/jumpserve-infra'])

    def boundaries():
        f.rejects(status)
        f.query('update platform_slack_bindings set enabled=true')
        assert status()['version'] == 'platform-slack-status-v1'
        assert status('UTHIRD')['version'] == 'platform-slack-status-v1'
        assert status(owner, 'DPRIVATE')['version'] == 'platform-slack-status-v1'
        for room, sender in [('COTHER','USECOND'),('DPRIVATE','USECOND'),(None,'USECOND'),(channel,None)]:
            f.rejects(lambda:status(sender, room))
        for role in ('anon','authenticated','service_role'):
            f.rejects(lambda:f.query('select public.platform_slack_authority('+','.join(map(q,(team,channel,owner)))+')',role=role))
        for role in ('anon','authenticated'):
            f.rejects(lambda:rpc('platform_slack_status',team,channel,owner,role=role))
            f.rejects(lambda:f.query('select * from platform_slack_bindings',role=role))
    f.check('Slack adapter requires enabled owner delegation and denies browser roles, wrong channels and other DMs', boundaries)

    def admission():
        ident, session = f.uid(), f.uid()
        first = request(ident, session); same = request(ident, session)
        assert first['task_id'] == same['task_id'] and same['replayed'] is True
        assert request()['task_id'] == first['task_id']
        assert f.query('select count(*) from platform_tasks where id='+q(first['task_id'])) == '1'
        assert f.query('select max_reserved_cents from platform_tasks where id='+q(first['task_id'])) == f.query("select max_spend_cents from autonomy_budget_categories where category='platform_manual'")
        for mutation in (dict(title='Different'),dict(actor=owner),dict(repositories=[])):
            changed = dict(task); changed.update(mutation)
            f.rejects(lambda:request(ident,session,changed))
        f.rejects(lambda:request(ident,f.uid()))
        f.rejects(lambda:request(ident,session,sender='UTHIRD'))
        state = status()
        assert first['task_id'] in [item['id'] for item in state['shared_tasks']]
        assert all(set(item) == {'id','title','status','cancel_requested','created_at','updated_at'} for item in state['shared_tasks'])
        f.query("update platform_tasks set status='cancelled',cancel_requested=true where id="+q(first['task_id']))
        retained = request(f.uid(),session)
        assert retained['task_id'] == first['task_id'] and retained['status']=='cancelled'
    f.check('Slack admission keeps category budgets, immutable request IDs and deduplicates active repeated work', admission)

    def privacy():
        private = dict(task, title='Synthetic private owner DM task')
        item = request(payload=private, sender=owner, room='DPRIVATE')
        assert item['task_id'] not in [t['id'] for t in status()['shared_tasks']]
        assert item['task_id'] in [t['id'] for t in status(owner,'DPRIVATE')['shared_tasks']]
        f.query("update platform_operators set role='revoked' where user_id="+q(delegated))
        f.rejects(status); f.rejects(request)
        f.query("update platform_operators set role='owner' where user_id="+q(delegated))
    f.check('shared status excludes owner DM tasks and revoked delegation immediately stops new reads and requests', privacy)

    def evidence():
        ident, call = f.uid(), f.uid(); sha='a'*64; path='slack/'+ident+'/'+sha
        def record(role='service_role', digest=sha): return rpc('platform_slack_record', ident,call,'model-request',digest,10,'slack/'+ident+'/'+digest,role=role)
        assert record()['recorded'] is True and record()['sha256']==sha
        f.rejects(lambda:record(digest='b'*64))
        for role in ('anon','authenticated'):
            f.rejects(lambda:record(role))
            f.rejects(lambda:f.query('select * from platform_slack_records',role=role))
        for role in ('anon','authenticated','service_role'):
            f.rejects(lambda:f.query('delete from platform_slack_records where id='+q(ident),role=role))
        f.rejects(lambda:f.query('delete from platform_slack_records where id='+q(ident)))
        assert f.query('select storage_path from platform_slack_records where id='+q(ident))==path
    f.check('original Slack model evidence is immutable, private and content-addressed', evidence)

    f.report.update(passed=True, protocol='platform-slack-gateway-v1')
    path=f.DIRECTORY/'platform-slack-report.json'; path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))


if __name__ == '__main__': main()
