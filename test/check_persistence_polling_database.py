"""Real PostgreSQL comparison against the pre-optimization dispatch RPC."""
import json
from pathlib import Path
import check_repair_contract_database as previous
import check_research_ideas_database as fixture

MIGRATION = '202611010005_dispatch_status_projection.sql'


def main():
    previous.main()
    fixture.report.update(protocol='persistence-polling-v1', passed=False)
    q = fixture.sql_text

    def snapshot():
        return fixture.query("select jsonb_build_object('dispatches',(select jsonb_agg(to_jsonb(d) order by id) from research_model_dispatches d),'calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c),'workflows',(select jsonb_agg(to_jsonb(w) order by study_id) from research_autonomy_workflows w),'budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b))")

    def results():
        return fixture.query("select jsonb_agg(public.research_model_dispatch('result',jsonb_build_object('id',id,'study_id',study_id)) order by id) from research_model_dispatches", role='service_role')

    before = snapshot()
    expected = results()
    if not expected or expected == 'null':
        raise AssertionError('Representative dispatch fixtures required.')
    fixture.query((fixture.ROOT/'database'/MIGRATION).read_text())

    def equivalent():
        if results() != expected or snapshot() != before:
            raise AssertionError('Projection changed original responses or retained state.')
    fixture.check('optimized result RPC equals original across every retained dispatch without changing calls deadlines or budgets', lambda: (equivalent() or dict(passed=True)))

    def access():
        for role in ('anon', 'authenticated', 'service_role'):
            if fixture.query("select has_function_privilege("+q(role)+",'public.research_model_dispatch_before_polling_v1(text,jsonb)','EXECUTE')") != 'f':
                raise AssertionError('Previous implementation must stay private.')
        for role in ('anon', 'authenticated'):
            if fixture.query("select has_function_privilege("+q(role)+",'public.research_model_dispatch(text,jsonb)','EXECUTE')") != 'f':
                raise AssertionError('Browser invocation must stay denied.')
        fixture.rejects(lambda: fixture.query("select public.research_model_dispatch('result',jsonb_build_object('id',gen_random_uuid(),'study_id',gen_random_uuid()))", role='service_role'))
        old = fixture.query("select public.research_model_dispatch_before_polling_v1('health','{}')")
        new = fixture.query("select public.research_model_dispatch('health','{}')", role='service_role')
        if old != new:
            raise AssertionError('Health/admission delegation changed.')
    fixture.check('private delegation browser denial absent identity and unchanged health semantics', lambda: (access() or dict(passed=True)))
    fixture.report['passed'] = True
    path = fixture.DIRECTORY/'persistence-polling-report.json'
    path.write_text(json.dumps(fixture.report, indent=2)+'\n')
    print(json.dumps(dict(passed=True, report=str(path), checks=len(fixture.report['checks']), provider_calls=0, production_mutations=0)))


if __name__ == '__main__':
    main()
