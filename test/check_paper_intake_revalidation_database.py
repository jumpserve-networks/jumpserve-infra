"""Audited retained-response recovery in isolated local Postgres, with no model calls."""
import copy
import json
import subprocess
import check_paper_dependencies_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    front = f.ROOT.parent / 'jumpserve-front-end'
    q = f.sql_text

    def node(code, value=None):
        result = subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', code], cwd=front, input=json.dumps(value), capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    fixture = node("""import {dependencyPaperCase as c} from './scripts/lib/paper-dependency-case.mjs';
import {referenceResponse} from './scripts/lib/paper-intake-cases.mjs';
import {paperModelRequest} from './lib/paper-intake-model.ts';
console.log(JSON.stringify({paper:c.paper,request:paperModelRequest(c.paper),response:{...referenceResponse(c.reference,c.reference_format),id:'resp_revalidation_fixture'}}));""")
    study = f.uid()
    f.query("select research_paper_intake('reserve'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(filename='Revalidation software fixture.pdf', sha256='a' * 64, byte_count=100)) + ')', role='service_role')
    token = f.uid()
    f.query("update research_paper_intakes set status='processing',submit_token=" + q(token) + "::uuid,provider_response_id='resp_revalidation_fixture',model_calls=1,reserved_cents=100,request=" + f.sql_json(fixture['request']) + ',paper_text=' + f.sql_json(fixture['paper']) + ',response=' + f.sql_json(fixture['response']) + ' where study_id=' + q(study))
    failed = json.loads(f.query("select research_paper_intake('failed'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(token=token, response=fixture['response'], reason='Document provenance or implementation choices are invalid.')) + ')', role='service_role'))
    f.query('update research_paper_intakes set deadline_at=deadline_at where study_id=' + q(study))
    # Read the actual full snapshot, including its revision and timestamps.
    failed = json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id=' + q(study)))
    code = """import {readFileSync} from 'node:fs';
import {retainedPaperRevalidation} from './lib/paper-intake-revalidation.ts';
import {paperIntakeRevalidationSQL} from './scripts/lib/paper-intake-revalidation-sql.mjs';
const row=JSON.parse(readFileSync(0,'utf8')),payload=retainedPaperRevalidation(row);
console.log(JSON.stringify({payload,sql:paperIntakeRevalidationSQL(row,payload)}));"""
    repair = node(code, failed)
    stale = copy.deepcopy(failed)
    stale['revision'] += 1
    assert f.query(node(code, stale)['sql']) == ''
    assert json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id=' + q(study))) == failed
    f.query(repair['sql'])
    after = json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id=' + q(study)))
    assert after['status'] == 'ready' and after['breakdown'] == repair['payload']['breakdown']
    for key in ['owner_id', 'source_id', 'original_artifact_id', 'text_artifact_id', 'sha256', 'paper_text', 'request', 'response', 'provider_response_id', 'submit_token', 'deadline_at', 'created_at', 'model_calls', 'reserved_cents']:
        assert after[key] == failed[key], key
    assert json.loads(f.query('select snapshot from research_paper_intake_events where study_id=' + q(study) + ' and revision=' + str(failed['revision']))) == failed
    assert after['revision'] == failed['revision'] + 2
    assert f.query("select count(*) from research_audit_events where study_id=" + q(study) + " and action='revalidate-paper-intake'") == '1'
    assert f.query('select status from research_paper_reviews where study_id=' + q(study)) == 'ready'
    f.query(repair['sql'])
    assert json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id=' + q(study))) == after
    assert f.query("select count(*) from research_audit_events where study_id=" + q(study) + " and action='revalidate-paper-intake'") == '1'
    for role in ['anon', 'authenticated', 'service_role']:
        f.rejects(lambda role=role: f.query(repair['sql'], role=role))
    for table in ['research_autonomy_tasks', 'research_model_dispatches', 'research_queue_jobs']:
        assert f.query('select count(*) from ' + table + ' where study_id=' + q(study)) == '0'
    print(json.dumps(dict(passed=True, database=f.DATABASE, checks=['stale snapshot cannot write', 'original failure preserved', 'atomic recovery uses existing RPC and triggers', 'provider identity, request, response and limits preserved', 'idempotent recovery', 'direct browser/service writes denied', 'no inference or experiment dispatch'])))


if __name__ == '__main__':
    main()
