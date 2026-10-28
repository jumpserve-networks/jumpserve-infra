"""Read-only replay of an assessment's recorded source-arithmetic calculations.

Uses public evidence only. Never starts jobs, invokes a model, writes Supabase,
downloads protected originals, changes labels or reconstructs an original PDF.
"""
import argparse
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import datetime as dt
import hashlib
import json
from pathlib import Path
import ssl
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import uuid

ROOT=Path(__file__).resolve().parents[1]
API='https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research'
VERSION='assessment-numeric-replay-v1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replay(config, rows):
    results=[]
    for calc in config['calculations']:
        matches=[r for r in rows if r['metric']==calc['id'] and r['observation_id']==calc['id']]
        base=dict(id=calc['id'],operation=calc['operation'],ordered_inputs=calc['inputs'])
        if len(matches)!=1:
            results.append(dict(base,status='missing' if not matches else 'ambiguous',reason='Expected one recorded calculation identity.')); continue
        m=matches[0]; cells={c['id']:c for c in m['details']['cells']}
        needed=calc['inputs']+([calc['reported_cell']] if calc['reported_cell'] else [])
        if m['status']!='recorded' or any(cells.get(k,{}).get('status')!='recorded' or cells[k].get('original_numeric_lexeme') is None for k in needed):
            results.append(dict(base,status='unavailable',reason='A required original recorded cell is unavailable; no zero imputation.')); continue
        with localcontext() as context:
            context.prec=250; context.rounding=ROUND_HALF_EVEN
            operands=[Decimal(cells[k]['original_numeric_lexeme'].replace(',','').replace('−','-')) for k in calc['inputs']]
            op=calc['operation']; unit=Decimal(1).scaleb(-calc['decimal_places'])
            if op=='difference':value=operands[1]-operands[0]
            elif op=='relative-percent-change':
                if operands[0]==0:
                    results.append(dict(base,status='invalid',reason='Zero baseline; undefined relative change.')); continue
                value=100*(operands[1]-operands[0])/operands[0]
            elif op=='strict-increase':value=Decimal(int(all(a<b for a,b in zip(operands,operands[1:]))))
            elif op=='mean':value=sum(operands)/len(operands)
            else:
                results.append(dict(base,status='unsupported',reason='Unknown operation; no expression evaluated.')); continue
            value=value.quantize(unit)
            reported=Decimal(1) if op=='strict-increase' else Decimal(cells[calc['reported_cell']]['original_numeric_lexeme'].replace(',','').replace('−','-')).quantize(unit)
            row=dict(base,status='recorded',measurement_id=m['id'],units=m['units'],operands=[str(v) for v in operands],recalculated=str(value),retained_result=m['value'],reported=str(reported),matches_retained=value==Decimal(str(m['value'])),matches_reported=value==reported)
            if op=='difference':row['reversed_operand_counterfactual']=str((operands[0]-operands[1]).quantize(unit))
            results.append(row)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--assessment',required=True,type=uuid.UUID); args=parser.parse_args()
    assessment=str(args.assessment); stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=ROOT/'.test-artifacts/autonomy-methods-v1'/assessment/stamp; output.mkdir(parents=True,exist_ok=False)
    protocol=dict(version=VERSION,assessment_id=assessment,frozen_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        question='Do independently implemented Decimal operations on the retained numeric lexemes agree with each frozen calculation and stored result?',
        comparison='Exact Decimal equality after frozen decimal_places with ROUND_HALF_EVEN. Operand order is baseline then treatment. Reversed-order difference is a labeled counterfactual, not a correction to original evidence.',
        data_origin='archived-data; redacted public projections of recorded evidence',
        replication='Deterministic census of returned source-arithmetic calculation identities; no stochastic sample or interval.',
        limits=dict(max_http_requests=31,timeout_seconds_per_request=30,max_bytes_per_response=4000000,max_pages_per_kind=10,model_calls=0,experiment_launches=0),
        exclusions='Unsupported operations and missing/invalid/ambiguous/non-recorded inputs remain explicitly unavailable. No failed result is replaced.',
        scope='Shares retained extracted-cell inputs with the original worker. Does not verify original PDF bytes, extraction correctness, complete source review, empirical networking results, causality or paper claims.',
        evaluator=dict(identity='Deterministic Python replay authored and inspected by Codex',type='AI',independence='Separate arithmetic implementation; same retained input cells and implementation author/reviewer. Not independent scientific or human review.'))
    tls=ssl.create_default_context()
    if sys.platform=='darwin' and Path('/etc/ssl/cert.pem').is_file():
        tls.load_verify_locations(cafile='/etc/ssl/cert.pem')
        protocol['tls']=dict(certificate_verification=True,additional_ca_bundle='/etc/ssl/cert.pem',ca_bundle_sha256=sha(Path('/etc/ssl/cert.pem').read_bytes()))
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    attempts=[]; inventory={}; requests=0
    def fetch(name,query):
        nonlocal requests
        if requests>=protocol['limits']['max_http_requests']:raise ValueError('HTTP request budget exhausted; no truncated inventory is complete.')
        url=API+'/studies/'+assessment+'/queue?'+urlencode(query); requests+=1
        attempt=dict(url=url,started_at=dt.datetime.now(dt.timezone.utc).isoformat())
        try:
            with urlopen(Request(url,headers={'Accept':'application/json'}),timeout=30,context=tls) as response:
                raw=response.read(4000001); attempt['http_status']=response.status
            if len(raw)>4000000:raise ValueError('Public response exceeds byte bound.')
            path=output/(name+'.json');path.write_bytes(raw)
            if sha(path.read_bytes())!=sha(raw):raise ValueError('Local retained-byte verification failed.')
            attempt.update(status='retrieved',sha256=sha(raw),bytes=len(raw),file=path.name)
            return json.loads(raw)
        except Exception as error:
            attempt.update(status='failed',error_type=type(error).__name__);raise
        finally:
            attempt['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();attempts.append(attempt)
            (output/'retrieval-attempts.json').write_text(json.dumps(attempts,indent=2)+'\n')
    snapshot=fetch('queue',dict(public='1',diagnostics='1'))
    if snapshot['study']['id']!=assessment:raise ValueError('Assessment identity differs.')
    for kind in ('configurations','measurements','runs'):
        values=[]; after=None
        for page in range(10):
            query=dict(public='1',records=kind,limit='100')
            if after:query['after']=after
            data=fetch(kind+'-'+str(page),query)
            if data['study_id']!=assessment or any(r['study_id']!=assessment for r in data['records']):raise ValueError('Record belongs to another assessment.')
            values.extend(data['records']);cursor=data.get('next_after')
            if not cursor:break
            if cursor==after:raise ValueError('Repeated record cursor.')
            after=cursor
        else:raise ValueError('Record page budget exhausted; inventory is incomplete.')
        if len({r['id'] for r in values})!=len(values):raise ValueError('Duplicate record identities.')
        inventory[kind]=values
    results=[]
    for run in inventory['runs']:
        if run.get('provenance',{}).get('runner')!='source-arithmetic-v1':continue
        identity=run['provenance']['configuration_identity']; configs=[c for c in inventory['configurations'] if c['identity']==identity]
        rows=[m for m in inventory['measurements'] if m['run_id']==run['id']]
        result=dict(run_id=run['id'],configuration=identity,run_status=run['status'])
        if len(configs)!=1:result.update(status='ambiguous',reason='Configuration is not uniquely identified by the public inventory.')
        else:result.update(status='replayed',calculations=replay(configs[0]['details']['test_config'],rows))
        results.append(result)
    report=dict(version=VERSION,assessment_id=assessment,title=snapshot['study']['title'],completed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        protocol_sha256=sha((output/'protocol.json').read_bytes()),script_sha256=sha(Path(__file__).read_bytes()),source_snapshots=attempts,
        inventory_counts={k:len(v) for k,v in inventory.items()},results=results,scientific_scope=protocol['scope'],
        usage=dict(http_requests=requests,retrieved_public_bytes=sum(a.get('bytes',0) for a in attempts),model_calls=0,experiment_launches=0,measured_charges_usd=None,estimated_charges_usd=None),
        production_changes=False)
    path=output/'report.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report=str(path),sha256=sha(path.read_bytes()),results=results,production_changes=False),indent=2))


if __name__=='__main__':main()
