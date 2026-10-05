"""Typed evidence selection and recorded-value rendering, never model-generated measurements."""
import json,math
from typing import Literal
from pydantic import BaseModel,Field
VERSION='reliable-renderer-v2';PATH='/module/reliable-sketch-study'
class ReliableAnswerPlan(BaseModel):
    topics:list[Literal['assessment','units','memory','weighted','theory','coverage','uncertainty','configuration','source','uncovered']]=Field(min_length=1,max_length=4)
    configuration_id:str|None=Field(default=None,max_length=90,pattern=r'^[A-Za-z0-9_.-]+$')
    reference_number:int|None=Field(default=None,ge=0,le=46)
def prepare_reliable_context(agent,question,evidence):
    if len(question)>4000:raise ValueError('Question exceeds4000characters')
    from uuid import uuid4
    key='reliable-'+str(uuid4())
    snapshot=dict(current_authenticated_user_question=question,analysis=evidence.get('meta',{}).get('analysis_version'),configuration_ids=evidence.get('configuration_ids',[]),claims=[{k:r.get(k) for k in ('id','description','assessment')} for r in evidence.get('claims',[])],source_notes=evidence.get('source_notes'))
    if len(json.dumps(snapshot))>16000:raise ValueError('Selector snapshot exceeds16000characters')
    # Model sees only bounded recent text; full owner/module history remains stored.
    recent=[{'role':r['role'],'content':[{'text':b['text'][:2000]} for b in r.get('content',[]) if isinstance(b,dict) and isinstance(b.get('text'),str)]} for r in agent.messages[-4:]]
    agent.messages=[r for r in recent if r['content']]
    agent.messages.extend([{'role':'user','content':[{'text':question}]},{'role':'assistant','content':[{'toolUse':dict(toolUseId=key,name='get_reliable_study_results',input={})}]},{'role':'user','content':[{'toolResult':dict(toolUseId=key,status='success',content=[{'json':snapshot}])}]}])
def num(value):
    if value is None:return 'missing'
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):raise ValueError('Invalid numerical evidence')
    return f'{value:,.4g}'
def render_reliable_answer(plan,evidence,literature_reader,configuration_reader):
    paragraphs=[];reads=[]
    def claim(identifier):
        rows=[c for c in evidence.get('claims',[]) if c['id']==identifier]
        if len(rows)!=1:return 'Claim evidence unavailable; missing is not zero.'
        c=rows[0];return f"**{c['description']}: {c['assessment']}** ({c['location']}). {c['evidence']} {c['limitation']}"
    if evidence.get('status')!='recorded':return 'Study evidence is unavailable. Missing values are not recorded zeros.',reads
    for topic in dict.fromkeys(plan.topics):
        if topic=='assessment':
            v=evidence['meta']['validation']['findings'];paragraphs.append(f"This limited assessment records {num(v['total_cpu_runs'])} CPU runs on three generated250,000-update streams, six algorithms and ten preselected hash seeds per configuration in two campaigns. It includes independent finite bucket checks and separate weighted-update controls. No archived author result vectors are available. Original trace curves and FPGA/Tofino measurements remain untested; this is not full paper validation.")
            paragraphs.extend([claim('memory'),claim('sensing')])
        elif topic=='units':paragraphs.append('Counts are positive unit updates; outliers are queried keys with absolute frequency error>25 count units. AAE is count units/key and ARE is dimensionless, both averaged over observed positive-frequency keys. Interval checks include observed keys and three absent probes. KiB=1,024bytes; paper MB/KB conventions are unspecified. Throughput is million updates/s or repeated queries/s; it is not Gbps or the switch Kbps frequency metric.')
        elif topic=='memory':paragraphs.append(claim('memory'));paragraphs.append('The main campaign uses nominal author-accounted budgets8/32/128KiB. The predeclared follow-up caps allocated counter arrays at those budgets; metadata/allocator overhead and RSS remain excluded. Compare matched input hashes and seeds, without selecting a best-performing seed.')
        elif topic=='weighted':paragraphs.extend([claim('weighted-code'),claim('lock-order'),'The weighted-control correction is a separate version. It changes min(key,remaining) to min(weight,remaining) and applies conservative counter saturation. Single-update examples do not establish correctness for all weighted streams; the unit-update campaigns use original code.'])
        elif topic=='theory':paragraphs.extend([claim('theory'),claim('confidence-product'),'Low-budget dropped updates can invalidate empirical intervals without disproving the theorem under its auxiliary-fallback, larger-constant and independent-hash assumptions. No empirical estimate of Delta<1e-10 or years of operation is supported.'])
        elif topic=='coverage':
            l=literature_reader();reads.append(dict(name='get_reliable_literature',input={}))
            paragraphs.append(f"Literature inventory: {l['total_source_records']} records, main paper plus{l['direct_references']} direct references and one artifact supplement. Review counts: "+', '.join(f'{k}={v}' for k,v in sorted(l['review_counts'].items()))+'. Retrieval/hash verification does not establish review. All reviews are AI inspection by the study implementer; no independent human review. Main AppendixA conditional proof steps and most direct-source figures/tables remain incompletely examined. No recursive bibliography expansion.')
        elif topic=='uncertainty':paragraphs.append('Median and min–max are descriptive ranges across ten preselected hash seeds on each fixed stream, not confidence intervals. Keys share counters, repeated queries share traffic, and the three fixed generated streams do not sample operational networks. No inferential95%interval or rare-event confidence bound is estimated from this design. An appropriately justified dependence-aware future design may support inference; numerical agreement alone is not correctness, causality or generalization.')
        elif topic=='configuration':
            if plan.configuration_id is None:paragraphs.append('Choose an exact recorded configuration ID from the results; no missing configuration is filled from published values.');continue
            r=configuration_reader(plan.configuration_id);reads.append(dict(name='get_reliable_configuration',input={'configuration_id':plan.configuration_id}))
            if r['status']!='recorded':paragraphs.append(f"Configuration {plan.configuration_id} is unavailable; missing measurements are not zero and paper values cannot fill them.");continue
            c=r['configuration'];s=r['summary'];paragraphs.append(f"Configuration {c['id']}: {c['algorithm']}, Zipf exponent{num(float(c['skewness']))}, budget{num(c['budget_bytes'])}bytes ({c['budget_regime']}); {s['recorded']}/{s['planned']}runs, failed{s['failed']}, excluded{s['excluded']}. Input SHA256 {c['input_sha256']}.")
            for m in ('outliers','aae','are','lost_mass','interval_violations','nominal_bytes','allocated_counter_bytes'):
                z=s['statistics'].get(m);paragraphs.append(f"{m}: median {num(z['median'])}, descriptive range {num(z['min'])}–{num(z['max'])} {z['units']}; recorded n={z['n']}." if z else f'{m}: missing.')
            paragraphs.append(f"Accuracy queries census {s['observed_keys']} distinct observed keys plus three absent probes; this does not cover an unlimited universe of absent keys.")
            paragraphs.append('Missing CM/CU bounds are not zero violations. Counter-memory caps exclude metadata/RSS. Fixed input/seed matching supports contrasts within this campaign, not original-paper agreement.')
        elif topic=='source':
            l=literature_reader(reference_number=plan.reference_number);reads.append(dict(name='get_reliable_literature',input={'reference_number':plan.reference_number}))
            for s in l['sources']:
                paragraphs.append(f"Ref{s['reference_number']}: {s['citation']} Access: {s['access_status']}; review: {s['review_status']}. Version: {s.get('retrieved_version') or 'unavailable'}. Original SHA256: {s.get('sha256') or 'unavailable'}. {s.get('findings') or 'No substantive review.'} {s['limitations']}")
        else:paragraphs.append('The requested broader conclusion is untested. No years-long deployment, causal application benefit, complete theorem verification, original trace reproduction, negative-weight/delete campaign or FPGA/Tofino operational validation is available. Such inputs or equipment were not invented.')
    return '\n\n'.join(paragraphs)+f'\n\n[Results]({PATH}/test-results) · [Methods]({PATH}/methods) · [Literature]({PATH}/literature). Analysis: reliable-assessment-v1.',reads

# Exact user-supplied configuration identifiers cannot be discarded by the topic model.
def constrain_reliable_plan(plan,question):
    import re
    identifier=re.search(r"(?:main|followup)-zipf[0-9]+(?:\.[0-9]+)?-[0-9]+-(?:RS_raw|RS|CM[0-9]+|CU[0-9]+)",question)
    if identifier:
        topics=['configuration']+[t for t in plan.topics if t!='configuration']
        return ReliableAnswerPlan(topics=topics[:4],configuration_id=identifier.group(0),reference_number=plan.reference_number)
    return plan
