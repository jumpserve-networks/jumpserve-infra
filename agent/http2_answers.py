"""AI selects typed evidence; scientific statements are rendered from recorded data."""
from collections import Counter
import json
from typing import Literal
from pydantic import BaseModel, Field

VERSION='http2-evidence-renderer-v2'
PATH='/module/http2-compliance-study'
Topic=Literal['units','configuration','coverage','uncertainty','discrepancy','rejection','scope','assessment','source','uncovered']

class HTTP2AnswerPlan(BaseModel):
    topics: list[Topic] = Field(min_length=1,max_length=4,description='Relevant evidence topics only; never write a narrative or new values.')
    configuration_id: str | None = Field(default=None,max_length=100,pattern=r'^[A-Za-z0-9.-]+$',description='Exact requested configuration; Apache-2.4.63 when an absent Apache fixture is queried.')
    reference_number: int | None = Field(default=None,ge=0,le=48)
    test_id: int | None = Field(default=None,ge=1,le=156)

def _number(value):
    if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Invalid recorded case count')
    return value

def _histogram(summary):
    counts=summary['author_counts']
    if not isinstance(counts,dict) or sum(_number(v) for v in counts.values())!=_number(summary['recorded']):
        raise ValueError('Incomplete recorded histogram')
    # Author histograms are sparse Counters over every recorded case. Only
    # after conservation is checked, an omitted category is a recorded zero.
    # Missing summary rows and published values never use this rule.
    return counts

def render_http2_answer(plan,evidence,literature_reader,configuration_reader):
    plan=HTTP2AnswerPlan.model_validate(plan)
    if not evidence.get('campaign'):return 'The recorded study is unavailable. Missing results cannot be replaced with zero or paper values.'
    summaries=evidence.get('summaries',[])
    primary=[s for s in summaries if s.get('published_counts') is not None]
    claims={c['claim_id']:c for c in evidence.get('claims',[])}
    paragraphs=[]
    def claim(identifier):
        row=claims.get(identifier)
        if row is None:return f'Recorded assessment for {identifier} is unavailable.'
        return f"{row['assessment'].capitalize()}: {row['evidence']} Limit: {row['limitation']}"
    for topic in dict.fromkeys(plan.topics):
        if topic=='units':
            paragraphs.append('RFC 9113 §4.1 specifies a **9-octet (72-bit)** frame header. Paper Table 1 agrees; §2.1 prose says 12 bytes, an expository error. HTTP status 500 is distinct from HTTP/2 error code **5 (STREAM_CLOSED)**. Error code **2 is INTERNAL_ERROR**, and **1 is PROTOCOL_ERROR**. [RFC 9113, ref 45]('+PATH+'/literature).')
        elif topic=='configuration':
            identifier=plan.configuration_id
            summary=next((s for s in summaries if s['configuration_id']==identifier),None)
            if summary is None:
                paragraphs.append('The requested configuration summary is **unavailable in the returned evidence**. That does not establish zero accepted cases. Apache 2.4.63 is in published Table 5 even when a fixture omits it. Published values cannot substitute for a missing reproduced value.')
            else:
                counts=summary['author_counts'];preserved=summary['preserved_counts']
                paragraphs.append(f"**{identifier}**: {_number(summary['recorded'])}/{_number(summary['planned'])} recorded cases; {_number(summary['missing'])} missing and {_number(summary['unknown'])} unknown. Author categories: `{json.dumps(counts,sort_keys=True)}`. Evidence-preserving categories: `{json.dumps(preserved,sort_keys=True)}`. Unknowns remain unknown; rejection is not compliance.")
                details=configuration_reader(identifier,offset=((plan.test_id-1)//50)*50 if plan.test_id else 0,limit=50)
                if details.get('status')=='unavailable':paragraphs.append('Further configuration/run details are unavailable.')
                elif plan.test_id:
                    row=next((m for m in details['measurements'] if m['test_id']==plan.test_id),None)
                    if row is None:paragraphs.append('The requested case is unavailable, not zero.')
                    else:paragraphs.append('Recorded case: `'+json.dumps({k:row.get(k) for k in ('test_id','side','rfc_section','expected','expected_scope','outcome','status','reason','error_code','observed_scope')},sort_keys=True)+'`. Error codes are dimensionless; null means unavailable. Scope/code need case-level RFC interpretation.')
                else:
                    config=details.get('configuration',{})
                    paragraphs.append('Recorded configuration: `'+json.dumps({k:config.get(k) for k in ('proxy','version','mode','tls','requested_resources','actual_resources')},sort_keys=True)+'`. Null fields remain unavailable. Additional per-test evidence is paginated; this answer does not claim a full-vector audit.')
        elif topic in ('coverage','source'):
            data=literature_reader(plan.reference_number if topic=='source' else None)
            sources=data.get('sources',[]);counts=Counter(s['review_status'] for s in sources)
            if topic=='source':
                if not sources:paragraphs.append('The requested source record is unavailable.')
                for row in sources:paragraphs.append(f"Ref {row['reference_number']}: {row['citation']} Review: **{row['review_status']}**; download: {row['download_status']}; version: {row['retrieved_version']}; SHA-256: {row.get('sha256') or 'unavailable'}. Source: {row.get('retrieved_url') or row['source_url']}.")
            else:
                paragraphs.append(f"Literature inventory: **{len(sources)} entries**, main paper plus direct citations. Complete: {counts['complete']}; partial: {counts['partial']}; unreviewed: {counts['unreviewed']}; unavailable: {counts['unavailable']}. **{len(sources)-counts['complete']} are not completely reviewed.** Download does not imply review; no recursive bibliography expansion. Independent historical proxy/cloud fleet replication remains untested. [Literature]({PATH}/literature).")
        elif topic=='uncertainty':
            paragraphs.append('The recorded protocol supports **descriptive counts**, with no predeclared population estimand or dependence model supporting a 95% confidence interval. Designed cases and same-host process repeats are correlated. This does not rule out every possible statistical model; it means an inferential interval is unsupported under this study protocol. Archived numerical reproduction is separate from fresh Node loopback endpoint controls. Neither proves universal compliance or independently validates the historical fleet.')
        elif topic=='rejection':
            total=sum(_number(s['recorded']) for s in primary)
            histograms=[_histogram(s) for s in primary]
            rejected=sum(_number(counts.get(k,0)) for counts in histograms for k in ('dropped','500','goaway','reset'))
            accepted=sum(_number(counts.get(k,0)) for counts in histograms for k in ('received','modified','unmodified'))
            drops=sum(_number(counts.get('dropped',0)) for counts in histograms)
            unknown=sum(_number(s['unknown']) for s in primary);overall=sum(_number(s['unknown']) for s in summaries)
            if not total:paragraphs.append('The primary counts are unavailable; no percentage is imputed.')
            else:paragraphs.append(f"**{rejected}/{total} = {100*rejected/total:.2f}% is the author rejection rate, not an RFC compliance rate.** Rejection includes {drops} silent drops; {accepted} outcomes are accepted under that classifier. **{unknown} primary and {overall} overall unknown outcomes remain unknown**, never zero or accepted in the preserved interpretation. A timeout does not establish its network cause or an RFC-correct error response.")
        elif topic=='discrepancy':
            paragraphs.extend([claim('figure8'),'Figure 8 accepted deltas are **H2H1 minus H2EE**, over 78 matched client cases. The released bug maps accepted H2EE cases to Dropped. A separate synthetic control diagnoses that bug; it does **not** establish which revision generated the camera-ready PDF, or prove that revision differed.',claim('figure7')])
        elif topic=='scope':
            paragraphs.append('RFC 9113 §5.4.1 permits escalation from a stream error to a connection error (GOAWAY). **GOAWAY alone does not establish noncompliance**; error-code semantics and case context matter. Unmatched historical configurations do not establish causal effects of TLS or RFC revision. Full independent physical proxy/cloud validation remains untested. [Methods]('+PATH+'/methods); [RFC 9113, ref 45]('+PATH+'/literature).')
        elif topic=='assessment':
            paragraphs.extend([claim('table5'),claim('figure7'),claim('figure8'),'Archived reanalysis, corrected exploratory calculations and fresh owned-loopback controls are distinct. Literature review and independent fleet reproduction remain incomplete. A verified finite counterexample **can** establish noncompliance, but this assessment has not independently validated the needed case-level semantics for that conclusion. Rejection is not compliance; no exploit, prevalence or causal TLS/RFC effect is established.'])
        elif topic=='uncovered':
            paragraphs.append('The recorded study does not cover this requested conclusion. It contains archived HTTP/2 protocol observations and separate owned-loopback endpoint controls, with partial literature review. No simulator/orbital results, current-provider measurement, exploit validation, population prevalence or independent historical proxy/cloud replication is available.')
    return '\n\n'.join(paragraphs)+f'\n\n[Recorded results]({PATH}/test-results) · [Methods and limitations]({PATH}/methods). Analysis: http2-assessment-v3.'

def save_rendered_message(agent,text,history_length=0):
    # Display and persist the validated rendered answer; retain the typed plan in
    # answer provenance separately. Never display incidental model prose/JSON.
    retained=[]
    for message in agent.messages[history_length:]:
        if message.get('role')=='assistant':
            message=dict(message,content=[block for block in message.get('content',[]) if not (isinstance(block,dict) and 'text' in block)])
            if not message['content']:continue
        retained.append(message)
    agent.messages=agent.messages[:history_length]+retained
    agent.messages.append({'role':'assistant','content':[{'text':text}]})
