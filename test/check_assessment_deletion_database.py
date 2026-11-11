"""Actual isolated Postgres deletion, ownership, RLS and concurrency checks."""
from concurrent.futures import ThreadPoolExecutor
import json
import check_research_ideas_database as f


def main():
    f.bootstrap(include_deleted_at=False)
    f.query("create schema auth; create table auth.users(id uuid primary key,is_anonymous boolean); create table auth.identities(user_id uuid references auth.users(id),provider text);")
    q=f.sql_text
    f.query("insert into auth.users values("+q(f.ACTOR)+",false),("+q(f.OTHER)+",false);insert into auth.identities values("+q(f.ACTOR)+",'google'),("+q(f.OTHER)+",'email');")
    for name in ('202611110001_next_paper_intake.sql','202611110002_assessment_deletion.sql'):
        f.query((f.ROOT/'database'/name).read_text())

    def create(status='uploaded',actor=f.ACTOR):
        study=f.uid()
        upload=dict(filename='Synthetic deletion fixture.pdf',sha256='a'*64,byte_count=100)
        f.query("select public.research_paper_intake('reserve',"+q(actor)+"::uuid,"+q(study)+"::uuid,"+f.sql_json(upload)+")",role='service_role')
        if status!='uploaded':f.query("update research_paper_intakes set status="+q(status)+" where study_id="+q(study))
        return study

    def delete(study,actor=f.ACTOR,role='service_role'):
        return json.loads(f.query('select public.research_delete_assessment('+q(actor)+'::uuid,'+q(study)+'::uuid)',role=role))

    def ownership():
        study=create()
        for actor in (f.OTHER,f.uid()):f.rejects(lambda:delete(study,actor))
        for role in ('anon','authenticated'):f.rejects(lambda:delete(study,role=role))
        non_google=create(actor=f.OTHER);f.rejects(lambda:delete(non_google,f.OTHER))
        assert f.query('select deleted_at is null from research_studies where id='+q(study))=='t'
    f.check('only the verified Google-linked owner can delete through the private RPC',ownership)

    def retained_and_idempotent():
        study=create()
        assert f.store.owns(study,f.ACTOR)
        assert not f.store.owns(study,f.OTHER)
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:delete(study),range(3)))
        assert all(result==dict(id=study,deleted=True) for result in results)
        assert f.query("select count(*) from research_audit_events where study_id="+q(study)+" and action='delete-assessment'")=='1'
        assert f.query('select status from research_paper_intakes where study_id='+q(study))=='cancelled'
        assert f.query('select model_calls from research_paper_intakes where study_id='+q(study))=='0'
        assert not f.store.owns(study,f.ACTOR)
        assert f.store.rows('studies',{'id':'eq.'+study})==[]
        assert f.query('select count(*) from research_paper_uploads where id='+q(study))=='1'
        f.rejects(lambda:f.query('update research_studies set deleted_at=null where id='+q(study),role='service_role'))
        f.rejects(lambda:f.query("update research_paper_intakes set reason='Resume deleted paper' where study_id="+q(study)))
        f.rejects(lambda:f.query("insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values(gen_random_uuid(),"+q(study)+",repeat('b',64),0,'synthetic','application/json','{}',clock_timestamp())",role='service_role'))
    f.check('concurrent deletion is idempotent, releases upload slots and fences restart',retained_and_idempotent)

    def rls():
        study=create(status='failed')
        # Simulate a published grant to prove the restrictive deletion policy
        # overrides permissive visibility without altering real publication rules.
        f.query('create policy deletion_fixture_public on research_studies for select to anon,authenticated using(id='+q(study)+'::uuid)')
        for role in ('anon','authenticated'):assert f.query('select count(*) from research_studies where id='+q(study),role=role)=='1'
        before=f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))
        delete(study)
        for role in ('anon','authenticated'):assert f.query('select count(*) from research_studies where id='+q(study),role=role)=='0'
        assert f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))==before
        assert f.query("select count(*) from research_studies where id="+q(study)+" and deleted_at is null",role='service_role')=='0'
    f.check('deletion hides shared SQL reads and retains original failed evidence unchanged',rls)

    def active():
        for status in ('submitting','processing','uncertain'):
            study=create(status=status);f.rejects(lambda:delete(study))
            assert f.query('select deleted_at is null from research_studies where id='+q(study))=='t'
        study=create()
        f.query("update research_paper_intakes set status='cancelled',model_calls=1,submit_token=gen_random_uuid() where study_id="+q(study))
        f.rejects(lambda:delete(study))  # A local cancel does not reconcile an unknown remote call.
        study=create(status='failed')
        f.query("insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256) values("+q(study)+",'{}',encode(sha256(convert_to('{}','UTF8')),'hex'))")
        f.rejects(lambda:delete(study))
        assert f.query("select count(*) from research_audit_events where study_id="+q(study)+" and action='delete-assessment'")=='0'
    f.check('active and uncertain work blocks deletion without partial changes',active)
    print(json.dumps(dict(passed=True,checks=f.report['checks'],database=f.DATABASE)))


if __name__=='__main__':main()
