"""Attach one fresh, read-only snapshot as a recorded tool result each turn."""
import json
from uuid import uuid4

def prepare_http2_context(agent,question,evidence):
    identifier='http2-snapshot-'+str(uuid4())
    # The model chooses evidence IDs; numeric facts are rendered from the full
    # fresh snapshot retained by the backend. Avoid repeatedly sending vectors
    # that the selector does not need. Explicit injection fixtures remain visible.
    selector_context={
      'snapshot_scope':'Evidence selection metadata; full measurements remain with backend rendering and read tools.',
      'campaign':{'id':evidence.get('campaign',{}).get('id'),'provenance':evidence.get('campaign',{}).get('provenance')},
      'configuration_ids':[s['configuration_id'] for s in evidence.get('summaries',[])],
      'claims':[{k:c.get(k) for k in ('claim_id','description','assessment')} for c in evidence.get('claims',[])],
      'warnings':evidence.get('warnings',[]),
      'source_notes':evidence.get('source_notes'),
    }
    agent.messages.extend([
      {'role':'user','content':[{'text':question}]},
      {'role':'assistant','content':[{'toolUse':{'toolUseId':identifier,'name':'get_http2_study_results','input':{}}}]},
      {'role':'user','content':[{'toolResult':{'toolUseId':identifier,'status':'success','content':[{'json':selector_context}]}}]},
    ])
