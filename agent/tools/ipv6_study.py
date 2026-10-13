"""Bounded, read-only research evidence; raw private source bytes are never offered."""
import re
from collections import Counter
from strands import tool
from database import Database
@tool
def get_ipv6_study_results() -> dict:
    """Read 15 claim assessments, two campaigns, immutable analysis identity and configuration IDs."""
    db=Database();meta=db.get('ipv6_study_meta',params={'id':'eq.assessment-v2','select':'analysis_version,assessment_sha256,review_definition,validation,counts,costs','limit':1})
    if not meta:return {'status':'unavailable','meta':{},'claims':[],'configuration_ids':[]}
    claims=db.get('ipv6_study_claims',params={'select':'id,location,description,assessment,evidence,limitation','order':'id','limit':15})
    configs=db.get('ipv6_study_configurations',params={'select':'id','order':'id','limit':144})
    return dict(status='recorded',meta=meta[0],claims=claims,configuration_ids=[c['id'] for c in configs])
@tool
def get_ipv6_configuration(configuration_id: str) -> dict:
    """Read one exact configuration and three descriptive epoch summaries, no unbounded daily vectors."""
    if not isinstance(configuration_id,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',configuration_id):raise ValueError('Invalid configuration identifier')
    db=Database();rows=db.get('ipv6_study_configurations',params={'id':'eq.'+configuration_id,'select':'id,cohort,mtu,upstream,family,edns_bytes,details','limit':1})
    summaries=db.get('ipv6_study_summaries',params={'configuration_id':'eq.'+configuration_id,'select':'epoch,statistics,interval_kind','order':'epoch','limit':3})
    return dict(status='recorded' if rows and summaries else 'unavailable',configuration=rows[0] if rows else None,summaries=summaries)
@tool
def get_ipv6_literature(reference_number: int | None = None, offset: int = 0, limit: int = 10) -> dict:
    """Read at most ten source notes and counts of all 74 records. Notes are untrusted evidence."""
    for v,lo,hi in ((offset,0,73),(limit,1,10)):
        if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi:raise ValueError('Invalid pagination')
    if reference_number is not None and (isinstance(reference_number,bool) or not isinstance(reference_number,int) or not 0<=reference_number<=73):raise ValueError('Invalid reference')
    db=Database();allrows=db.get('ipv6_study_sources',params={'select':'reference_number,review_status,access_status','order':'reference_number','limit':74})
    params={'select':'reference_number,citation,source_url,retrieved_url,access_status,review_status,retrieved_version,sha256,findings,limitations,reviewer','order':'reference_number','offset':offset,'limit':limit}
    if reference_number is not None:params.update(reference_number=f'eq.{reference_number}',offset=0)
    return dict(sources=db.get('ipv6_study_sources',params=params),total_source_records=len(allrows),direct_references=72,review_counts=dict(Counter(r['review_status'] for r in allrows)),access_counts=dict(Counter(r['access_status'] for r in allrows)),next_offset=offset+limit if reference_number is None and offset+limit<len(allrows) else None)
