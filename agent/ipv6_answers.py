"""Model selects evidence topics; the server renders scientific statements from saved records."""
import json,re
from typing import Literal
from pydantic import BaseModel,Field
from reliable_answers import num
VERSION='ipv6-renderer-v2';PATH='/module/ipv6-dns-study'
class IPv6AnswerPlan(BaseModel):
    topics:list[Literal['assessment','units','coverage','uncertainty','discrepancy','standards','causality','configuration','source','uncovered']]=Field(min_length=1,max_length=4)
    configuration_id:str|None=Field(default=None,max_length=100,pattern=r'^[A-Za-z0-9_.-]+$')
    reference_number:int|None=Field(default=None,ge=0,le=73)
def prepare_ipv6_context(agent,question,evidence):
    if len(question)>4000:raise ValueError('Question exceeds 4000 characters')
    snapshot=dict(current_authenticated_user_question=question,configuration_ids=evidence.get('configuration_ids',[]),claims=[{k:c.get(k) for k in ('id','description','assessment')} for c in evidence.get('claims',[])],source_notes=evidence.get('source_notes'))
    if len(json.dumps(snapshot))>16000:raise ValueError('Selector snapshot exceeds 16000 characters')
    recent=[{'role':r['role'],'content':[{'text':b['text'][:2000]} for b in r.get('content',[]) if isinstance(b,dict) and isinstance(b.get('text'),str)]} for r in agent.messages[-4:]]
    agent.messages=[r for r in recent if r['content']]
    agent.messages.extend([{'role':'user','content':[{'text':question}]},{'role':'assistant','content':[{'text':'I will select a typed plan from the recorded evidence; external function calls are unavailable.'}]},{'role':'user','content':[{'text':json.dumps(snapshot)}]}])
def constrain_ipv6_plan(plan,question):
    identifier=re.search(r'(?:no-dnssec|dnssec)--mtu[0-9A-Za-z-]+-(?:(?:lgi|no-lgi)-)?(?:v4-only|v6-only|ds)-edns[0-9]+',question)
    reference=re.search(r'(?:reference|ref)\s*\[?(\d+)\]?',question,re.I)
    topics=plan.topics;config=plan.configuration_id;ref=plan.reference_number
    if identifier:config=identifier.group(0);topics=['configuration']+[t for t in topics if t!='configuration']
    if reference and 0<=int(reference.group(1))<=73:ref=int(reference.group(1));topics=['source']+[t for t in topics if t!='source']
    return IPv6AnswerPlan(topics=topics[:4],configuration_id=config,reference_number=ref)
def render_ipv6_answer(plan,evidence,literature_reader,configuration_reader):
    if evidence.get('status')!='recorded':return 'Study evidence unavailable. Missing observations are not recorded zeros.',[]
    paragraphs=[];reads=[]
    def claim(identifier):
        rows=[c for c in evidence['claims'] if c['id']==identifier]
        if len(rows)!=1:return 'Claim evidence unavailable; missing is not zero.'
        c=rows[0];return f"**{c['description']}: {c['assessment']}** ({c['location']}). {c['evidence']} {c['limitation']}"
    for topic in dict.fromkeys(plan.topics):
        if topic=='assessment':
            v=evidence['meta']['validation'];paragraphs.append(f"{v['reproduced_cells']}/{v['published_cells']} absolute cells in Figures 13–15 agree within 0.0051 percentage points. The released fold and independent arithmetic agree on the same daily summaries. All 158 calendar dates and 144 configurations were retained: 145 available epoch days, two unavailable days and 11 excluded transition/boundary days. This is archived 2025 author-data reanalysis with finite controls, not new measurements, simulation or full paper validation.");paragraphs.append(claim('readiness-weighting'))
        elif topic=='units':paragraphs.append('TIMEOUT and SERVFAIL are percentages of recorded NS-set outcomes. Packet metrics use observed UDP server identities. TCP fallback is TCP/UDP × 100, a ratio that can exceed 100%, not a mutually exclusive event fraction. IPv6−IPv4 contrasts are percentage points (pp), not relative percent change. EDNS payload and MTU are bytes. These are neither Gbps nor file completion times; denominators cannot be interchanged.')
        elif topic=='coverage':
            l=literature_reader();reads.append(dict(name='get_ipv6_literature',input={}))
            paragraphs.append(f"{l['total_source_records']} source records: main paper, {l['direct_references']} direct references and one author artifact. Review counts: "+', '.join(f'{k}={v}' for k,v in sorted(l['review_counts'].items()))+'. Retrieval and hash verification do not establish review completeness. All reviews are AI inspection by the implementer, not human or independent review. Main dense relative heatmaps, all per-point series and packet-size distributions remain incomplete; many direct-source figures/tables/appendices are unreviewed. No recursive bibliography expansion.')
        elif topic=='uncertainty':paragraphs.append('Daily min–max ranges are descriptive, not confidence intervals. Daily panels reuse NS sets, servers and paths; a changing convenience sample from one AS is not independent sampling of Internet users. No justified inferential 95% CI or causal confidence bound is available. Matched configuration/date IPv6−IPv4 comparisons describe recorded conditions only. Missing April 21 and August 26 archives and a July 31 packet configuration remain missing, not zero. Denominator pooling and routing-anomaly exclusions are sensitivity analyses, not new independent replications.')
        elif topic=='discrepancy':paragraphs.extend([claim('rq3-fragments'),claim('analysis-defects'),'Finite controls demonstrate replacement of distinct answer groups, status conflation, a maximum used as a mean, and failure on empty duration lists. The correction is separate and was not substituted into historical summaries. Released-code defects do not establish the published generating revision, occurrence frequency or numerical impact.'])
        elif topic=='standards':paragraphs.append(claim('rfc3901'));paragraphs.append('RFC 3901 Section 4 recommends at least one IPv4-reachable authoritative server using SHOULD. This is not an unconditional two-server requirement. RFC 9715 is informational guidance; summary agreement does not establish implementation compliance.')
        elif topic=='causality':paragraphs.extend([claim('rq4-causality'),claim('rq5-dnssec'),'Observed-signature DNSSEC cohorts are not randomized; before/after LGI windows also change time and routing. A packet-drop mechanism or broader operational improvement was not experimentally isolated. RFC 7872 probes differ in epoch, transport, population and direction; their results are not matched replications of this campaign.'])
        elif topic=='configuration':
            if plan.configuration_id is None:paragraphs.append('Choose an exact recorded configuration ID. Missing results cannot be filled from the paper.');continue
            r=configuration_reader(plan.configuration_id);reads.append(dict(name='get_ipv6_configuration',input={'configuration_id':plan.configuration_id}))
            if r['status']!='recorded':paragraphs.append(f"Configuration {plan.configuration_id} unavailable; missing is not recorded zero.");continue
            c=r['configuration'];paragraphs.append(f"Configuration {c['id']}: {c['cohort']}, {c['mtu']}, {c['upstream']}, {c['family']}, EDNS {c['edns_bytes']} bytes. Historical summary reanalysis only.")
            for s in r['summaries']:
                for metric in ('TIMEOUT','udp_fragments'):
                    z=s['statistics'][metric];paragraphs.append(f"{s['epoch']} {metric}: daily mean {num(z['mean'])}%, descriptive min–max {num(z['min'])}–{num(z['max'])}%; {z['n']}/{z['planned']} valid/calendar days, missing {z['missing']}, invalid {z['invalid']}; pooled {num(z['pooled'])}%; matched IPv6−IPv4 {num(z['paired_v6_minus_v4_mean_pp'])} pp on {z['paired_days']} days.")
            paragraphs.append('NS-set outcome and UDP-server denominators differ. Descriptive ranges are not confidence intervals; zero paired-day count for IPv4/dual-stack is inapplicable, not a zero IPv6 effect.')
        elif topic=='source':
            l=literature_reader(reference_number=plan.reference_number);reads.append(dict(name='get_ipv6_literature',input={'reference_number':plan.reference_number}))
            if plan.reference_number is None:
                paragraphs.append(f"{l['total_source_records']} source records: main paper, {l['direct_references']} direct references and one author artifact. Review counts: "+', '.join(f'{k}={v}' for k,v in sorted(l['review_counts'].items()))+'. Retrieval and hash verification do not establish review completeness.')
            for s in l['sources']:paragraphs.append(f"Ref {s['reference_number']}: {s['citation']} Access: {s['access_status']}; review: {s['review_status']}. Version: {s.get('retrieved_version') or 'unavailable'}. Original-byte SHA256: {s.get('sha256') or 'unavailable'}. {s.get('findings') or 'No substantive content review.'} {s['limitations']}")
        else:paragraphs.append('Broader readiness, universal reachability, standards compliance, causal policy benefit, original raw-pcap packet-size reconstruction, APNIC client-data reanalysis and historical BGP interventions are untested or inconclusive. No current Internet scan, equipment, historical inputs or confidence interval was invented to fill these gaps.')
    return '\n\n'.join(paragraphs)+f'\n\nSource reviews: Codex implementer (AI), not human or independent review. [Results]({PATH}/test-results) · [Methods]({PATH}/methods) · [Literature]({PATH}/literature). Analysis: ipv6-dns-assessment-v1.',reads
