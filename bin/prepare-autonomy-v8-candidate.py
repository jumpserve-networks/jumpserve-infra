"""Prepare the v8 draft without rewriting the failed v7 candidate or its guard."""
import hashlib,json,re,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT.parent/'jumpserve-back-end/research_workflow'

def main():
 seed=json.loads((ROOT/'database/seed-autonomy-v7.json').read_bytes())
 seed.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:research-autonomy-v8')),version='research-autonomy-v8',created_by='Codex AI implementer; deterministic context-access correction',updated_by='Codex AI implementer; deterministic context-access correction')
 seed['system_prompt']+='''

RESOURCE AND READ GUARDS v8: Before selecting work, check remaining_commitment_cents. A value of zero means action blocked, reason resource-limit, kind capacity, detail resource-exhausted, and the exact required_input from the capacity contract. Coverage inventories identify retained records; they do not authorize another call or execution. Never select an inventory check when this resource guard applies.
A complete inline candidate.protocol is already supplied to a fresh review. Review those exact bytes now; do not request the identical protocol again. The server excludes inspect in that situation. A retained-protocol-reference is different: inspect every required fragment before readiness. A supplied complete evidence_read page is already available evidence; do not request that identical page again without a specific unresolved identity issue. Missing recorded observations remain missing. When the supplied evidence is incomplete and controller_numeric_check is null, assessment is inconclusive within the declared scope, regardless of the literal difference between a recorded zero and a reference value. The controller includes valid matched discrepancies from earlier partial runs when later compatible evidence supplies full union coverage; do not discard those discrepancies to prefer later agreement.
'''
 (ROOT/'database/seed-autonomy-v8.json').write_text(json.dumps(seed,indent=2)+'\n')
 fields=['id','version','module_id','system_prompt','research_context','created_by','updated_by'];quote=lambda s:"'"+s.replace("'","''")+"'"
 (ROOT/'database/202610190005_autonomy_prompt_v8.sql').write_text('begin;\ninsert into public.agent_prompt_versions('+','.join(fields)+') values('+','.join(quote(seed[f]) for f in fields)+');\nnotify pgrst,\'reload schema\';\ncommit;\n')
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());manifest['version']=25
 manifest['files']={name:hashlib.sha256((BACKEND/name).read_bytes()).hexdigest() for name in manifest['files']}
 (ROOT/'research-workflow-runtime.json').write_text(json.dumps(manifest,indent=2)+'\n')
 cases=json.loads((ROOT/'test/autonomy-followup-cases-v2.json').read_bytes());original=(ROOT/'database/202610190003_autonomy_v7_publication_guard.sql').read_text()
 guard=original.replace('before_autonomy_v7','before_autonomy_v8').replace("'research-autonomy-v7'","'research-autonomy-v8'").replace("'8'::jsonb","'9'::jsonb").replace('All eight','All nine')
 guard=re.sub(r'required text\[\]=array\[[^\]]+\]',"required text[]=array["+','.join(quote(c['name']) for c in cases['cases'])+']',guard)
 guard=re.sub(r"p_report->>'cases_sha256' is distinct from '[a-f0-9]{64}'","p_report->>'cases_sha256' is distinct from '"+hashlib.sha256((ROOT/'test/autonomy-followup-cases-v2.json').read_bytes()).hexdigest()+"'",guard)
 guard=re.sub(r"p_report->'input_sha256' is distinct from '[^']+'::jsonb","p_report->'input_sha256' is distinct from '"+json.dumps(manifest['files'],sort_keys=True,separators=(',',':'))+"'::jsonb",guard)
 (ROOT/'database/202610190006_autonomy_v8_publication_guard.sql').write_text(guard)
 print(json.dumps(dict(draft=seed['version'],published=False,runtime_files=len(manifest['files']))))

if __name__=='__main__':main()
