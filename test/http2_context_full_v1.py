"""Attach one fresh, read-only snapshot as a recorded tool result each turn."""
import json
from uuid import uuid4

def prepare_http2_context(agent,question,evidence):
    identifier='http2-snapshot-'+str(uuid4())
    agent.messages.extend([
      {'role':'user','content':[{'text':question}]},
      {'role':'assistant','content':[{'toolUse':{'toolUseId':identifier,'name':'get_http2_study_results','input':{}}}]},
      {'role':'user','content':[{'toolResult':{'toolUseId':identifier,'status':'success','content':[{'json':evidence}]}}]},
    ])
