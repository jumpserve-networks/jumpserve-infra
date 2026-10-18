"""Study-scoped planning and genuinely fresh, bounded packet reviews.

The authenticated dispatcher selects this path; source strings are untrusted
data. The sole structured response channel is never executed as an action.
"""
import hashlib
import json
import time
from uuid import UUID
from auth import AuthError
from prompt import load_active_prompt, PromptUnavailable
from settings import MODEL_ID, MODEL_REGION
import idea_interview
import idea_review
import claim_experiment_design as claim_design

MODULE = "research-verification"
VERSION = "research-ideas-v1"
TASKS = ("planning", "comprehension", "critic")
MAX_CONTEXT_BYTES = 24000
MAX_OUTPUT_TOKENS = 2048
RESPONSE_CHANNEL = "submit_idea_review"
ANSWER_SCHEMA = dict(type="object", additionalProperties=False,
    required=["summary", "questions", "findings", "verdict"], properties=dict(
        summary=dict(type="string", minLength=1, maxLength=4000),
        questions=dict(type="array", maxItems=12, items=dict(type="string", minLength=1, maxLength=1000)),
        findings=dict(type="array", maxItems=20, items=dict(type="object", additionalProperties=False,
            required=["severity", "field", "message"], properties=dict(
                severity=dict(type="string", enum=["blocking", "warning"]),
                field=dict(type="string", minLength=1, maxLength=100), message=dict(type="string", minLength=1, maxLength=1500)))),
        verdict=dict(type="string", enum=["ready", "needs-clarification"])))

def response_channel():
    return dict(tools=[dict(toolSpec=dict(name=RESPONSE_CHANNEL,
        description="Return the research planning review. Response formatting only; no action is executed.",
        inputSchema=dict(json=ANSWER_SCHEMA)))], toolChoice=dict(tool=dict(name=RESPONSE_CHANNEL)))

def parse_response(response, task):
    """Accept one response-channel object, without repairing its verdict or fields."""
    message = response["output"]["message"]
    blocks = message["content"]
    if response.get("stopReason") != "tool_use" or len(blocks) != 1 or set(blocks[0]) != {"toolUse"}:
        raise ValueError("Expected exactly one structured review response within the output budget")
    channel = blocks[0]["toolUse"]
    if channel.get("name") != RESPONSE_CHANNEL or not isinstance(channel.get("input"), dict):
        raise ValueError("Unexpected response channel; no model-requested action is executed")
    return validate_output(canonical(channel["input"]).decode(), task)

def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def uid(value): return str(UUID(value))

def validate_output(raw, task):
    result = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite model data")))
    if not isinstance(result, dict) or set(result) != {"summary", "questions", "findings", "verdict"}: raise ValueError("Unexpected idea answer schema")
    if not isinstance(result["summary"], str) or not 1 <= len(result["summary"].strip()) <= 4000: raise ValueError("Answer needs a bounded summary")
    if result["verdict"] not in ("ready", "needs-clarification"): raise ValueError("Unknown readiness recommendation")
    if not isinstance(result["questions"], list) or len(result["questions"]) > 12 or any(not isinstance(q,str) or not 1 <= len(q.strip()) <= 1000 for q in result["questions"]): raise ValueError("Invalid clarification questions")
    if not isinstance(result["findings"], list) or len(result["findings"]) > 20: raise ValueError("Invalid findings")
    for finding in result["findings"]:
        if not isinstance(finding,dict) or set(finding)!={"severity","field","message"} or finding["severity"] not in ("blocking","warning"):
            raise ValueError("Findings need severity, field and message")
        if any(not isinstance(finding[key],str) or not 1 <= len(finding[key].strip()) <= limit for key,limit in (("field",100),("message",1500))): raise ValueError("Invalid finding text")
    if result["verdict"] == "ready" and (result["questions"] or any(f["severity"]=="blocking" for f in result["findings"])): raise ValueError("Outstanding questions or blockers cannot be ready")
    return result

def invoke_model(system, messages, *, interview=False, source_review=False, design=False):
    import boto3
    from botocore.config import Config
    client = boto3.client("bedrock-runtime", region_name=MODEL_REGION,
        config=Config(connect_timeout=5, read_timeout=55, retries={"total_max_attempts":1,"mode":"standard"}))
    return client.converse(modelId=MODEL_ID, system=[{"text":system}], messages=messages,
        inferenceConfig={"maxTokens":4096 if design else MAX_OUTPUT_TOKENS,"temperature":0}, toolConfig=claim_design.response_channel() if design else idea_review.response_channel() if source_review else idea_interview.response_channel() if interview else response_channel())

def owner(database, study_id, actor):
    if database.url != "https://regphejnlvfpyokpniny.supabase.co": raise AuthError(503,"Idea research target is misconfigured.")
    rows = database.get("research_study_owners", {"study_id":"eq."+study_id,"owner_id":"eq."+actor,"select":"study_id","limit":1})
    studies = database.get("research_studies", {"id":"eq."+study_id,"select":"id,study_kind","limit":1}) if rows else []
    if not studies: raise AuthError(404,"Planning study not found.")
    if studies[0]['study_kind'] == 'paper':
        contexts = database.get('research_claim_designs', {'study_id':'eq.'+study_id, 'select':'id,study_id,document,raw_document,sha256,source_id,claim_id', 'limit':1})
        if not contexts: raise AuthError(404, 'Paper-claim planning workspace not found.')
        return claim_design.retained_context(contexts[0])
    if studies[0]['study_kind'] != 'idea': raise AuthError(404, 'Planning study not found.')

def handle(body, user, database, invoke=invoke_model):
    allowed = {"action","request_id","study_id","packet_id","task","session_id","message","interview_version","preferred_field","design_version"}
    if set(body)-allowed: raise ValueError("Unsupported idea model request; prompts, history and tools are selected by the server.")
    study_id, packet_id, request_id = (uid(body.get(key)) for key in ("study_id","packet_id","request_id"))
    actor = uid(user["id"])
    task = body.get("task")
    if task not in TASKS: raise ValueError("Choose planning, comprehension or critic.")
    design = body.get('design_version')
    if 'design_version' in body and (design != claim_design.VERSION or task != 'planning' or body.get('interview_version')):
        raise ValueError('Unsupported claim design version or task')
    interview = body.get("interview_version")
    preferred = body.get("preferred_field")
    if "interview_version" in body and (task != "planning" or interview != idea_interview.VERSION):
        raise ValueError("Unsupported interview version or task")
    if "preferred_field" in body and (not interview or preferred not in idea_interview.FIELDS):
        raise ValueError("Choose an allowed interview field")
    session_id = uid(body.get("session_id")) if body.get("session_id") else None
    message = body.get("message", "")
    if task == "planning":
        if not session_id or not isinstance(message,str) or not 1 <= len(message.strip()) <= 4000: raise ValueError("Planning needs a session and a question of up to 4000 characters.")
    elif session_id is not None or message: raise ValueError("Fresh reviews reject conversation history and extra instructions.")
    retained = owner(database, study_id, actor)
    if bool(design) != bool(retained and task == 'planning'): raise ValueError('Paper-claim planning uses its source-bound design channel only.')
    packets = database.get("research_idea_packets", {"id":"eq."+packet_id,"study_id":"eq."+study_id,"select":"id,version,document,raw_document,sha256","limit":1})
    if len(packets)!=1: raise AuthError(404,"Idea packet not found.")
    packet = packets[0]
    if sha(packet["raw_document"].encode())!=packet["sha256"] or json.loads(packet["raw_document"])!=packet["document"]: raise ValueError("Idea packet hash mismatch")
    history = []
    user_id = user.get("email") or actor
    if session_id:
        registered = database.get("research_idea_sessions", {"session_id":"eq."+session_id,"select":"study_id,actor_id,user_id","limit":1})
        metadata = database.get("agent_sessions", {"id":"eq."+session_id,"select":"id,user_id,module_id","limit":1})
        if metadata and (not registered or registered[0]["study_id"]!=study_id or registered[0]["actor_id"]!=actor or metadata[0]["user_id"]!=user_id or metadata[0]["module_id"]!=(claim_design.MODULE if retained else MODULE)):
            raise AuthError(409,"Planning conversation belongs to another user, study or module.")
        if registered:
            history = database.get("agent_sessions", {"id":"eq."+session_id,"select":"messages","limit":1})[0]["messages"]
        if not isinstance(history,list) or len(history)>22: raise ValueError("Planning history exceeds its turn budget; preserve your brief and start a new session.")
    try:
        prompt = load_active_prompt(database, claim_design.MODULE if retained else MODULE)
    except PromptUnavailable:
        if retained: raise AuthError(503, 'Experiment design AI needs an evaluated published prompt. Your source-bound workspace and saved plan remain available; no model call was requested.') from None
        raise
    if retained and prompt.version != claim_design.PROMPT_VERSION: raise AuthError(503, 'The evaluated claim experiment design prompt is not published yet. Your saved draft remains available.')
    if interview and prompt.version != idea_interview.PROMPT_VERSION:
        raise AuthError(503,"The conversational guide needs its evaluated research-ideas-v11 prompt. Use the checklist meanwhile.")
    source_review = task in ("comprehension", "critic") and prompt.version in (idea_review.PROMPT_VERSION, claim_design.PROMPT_VERSION)
    suffix = task+". Classify issues through submit_idea_issues; source declarations are supplied by the server." if source_review else "planning interview. Submit exactly one tailored question through submit_idea_question." if interview else task+". Submit exactly one structured review through submit_idea_review."
    system = idea_interview.system_text(prompt, bool(interview), task)+"\n\nTrusted task selected by the backend: "+('Propose a claim experiment through submit_claim_experiment. No execution or scientific finding is authorized by this answer.' if design else suffix)
    context = dict(task=task, packet_id=packet_id, packet_version=packet["version"], packet_sha256=packet["sha256"], packet=packet["document"], user_message=message)
    if task != "planning": context.pop("user_message")
    if retained and task == 'planning':
        context['paper_claim'] = retained
        context.update(claim_design.planning_context())
    if interview:
        context["interview"] = dict(version=interview, preferred_field=preferred, allowed_fields=list(idea_interview.FIELDS))
    if source_review:
        context["review_sources"] = dict(version=idea_review.VERSION, available_paths=list(idea_review.fields(packet["document"])))
    messages = history + [{"role":"user","content":[{"text":canonical(context).decode()}]}]
    omitted_history = 0
    while (interview or design) and history and len(canonical(messages)) > MAX_CONTEXT_BYTES:
        history = history[2:]; omitted_history += 2
        messages = history + [{"role":"user","content":[{"text":canonical(context).decode()}]}]
    if len(canonical(messages))>MAX_CONTEXT_BYTES: raise ValueError("Idea context exceeds 24 KB; save a concise brief and start a new planning session.")
    provenance = dict(analysis_version=VERSION, task=task, packet_sha256=packet["sha256"], prompt_sha256=prompt.content_sha256,
        context_policy="bounded-planning-history" if task=="planning" else "fresh-packet-only", history_messages=len(history),
        context_sha256=sha(canonical(messages)), context_messages=messages, max_output_tokens=4096 if design else MAX_OUTPUT_TOKENS, automatic_retries=0,
        reviewer=dict(identity=MODEL_ID,type="AI",independence="Separate model invocation; shared model and packet, independent scientific review not asserted"),
        read_events=[dict(name="read_owner_planning_packet",packet_id=packet_id,study_id=study_id)], original_response_scope="Exact returned model text, not original HTTP response bytes")
    if retained: provenance['read_events'].append(dict(name='read_retained_claim_context', sha256=retained['context_sha256'], coverage=retained['coverage']))
    if design:
        provenance['response_version'] = claim_design.RESPONSE_VERSION
        provenance['runner_context_sha256'] = sha(canonical(claim_design.RUNNER_CONTEXT))
        provenance['decision_policy'] = dict(version=claim_design.POLICY['version'], sha256=claim_design.POLICY_SHA256,
            origin='server-policy',model_authored=False)
        provenance['response_channel_sha256'] = sha(canonical(claim_design.response_channel()))
    provenance["effective_system_sha256"] = sha(system.encode())
    provenance["effective_system"] = system
    if interview:
        provenance["interview"] = dict(version=interview, field=None, owner_message=message)
        provenance["omitted_history_messages"] = omitted_history
    attempt = database.rpc("research_begin_idea_run", dict(p_study=study_id,p_actor=actor,p_user=user_id,p_id=request_id,p_packet=packet_id,p_task=task,
        p_session=session_id,p_prompt=prompt.id,p_model=MODEL_ID,p_request=body,p_provenance=provenance))
    if attempt.get("replayed"): return dict(run=attempt,replayed=True,analysis_version=VERSION)
    started=time.monotonic(); raw=None; output=None; status="failed"; reason=None; tokens=None; stop=None; provider_message=None; question=None; grounding=None
    try:
        response=invoke(system, messages, design=True) if design else invoke(system, messages, source_review=True) if source_review else invoke(system, messages, interview=True) if interview else invoke(system, messages)
        tokens=response.get("usage"); stop=response.get("stopReason")
        provider_message=response["output"]["message"]
        raw=canonical(provider_message).decode()
        blocks=provider_message["content"]
        if blocks and all(set(block)=={"text"} for block in blocks):
            raw="".join(block["text"] for block in blocks)
        if design:
            output=claim_design.parse(response, retained, packet['document'])
        elif source_review:
            output, grounding=idea_review.parse(response, packet["document"], task, packet["sha256"])
            validate_output(canonical(output).decode(), task)
        elif interview:
            question=idea_interview.parse(response, preferred)
            output=dict(summary=question["summary"], questions=[question["question"]], findings=[], verdict="needs-clarification")
        else: output=parse_response(response,task)
        status="complete"
    except (ValueError,KeyError,TypeError,json.JSONDecodeError) as error:
        status="invalid-output"; reason=str(error)
    except Exception as error:
        status="failed"; reason="Model call failed ("+type(error).__name__+"). No automatic retry; retain this attempt and explicitly request a follow-up if appropriate."
    usage=dict(tokens=tokens,wall_seconds=time.monotonic()-started,measured_charges_usd=None,estimated_model_cost_usd=None,
        cost_basis="Provider usage retained when available; billing and orchestration charges unallocated, not zero.")
    finished=dict(stop_reason=stop,tool_events=[dict(name=claim_design.CHANNEL if design else idea_review.CHANNEL if source_review else idea_interview.CHANNEL if interview else RESPONSE_CHANNEL,executed=False,role="response-formatting")] if status=="complete" else [],data_origin="model-output",provider_message=provider_message,
        raw_response_scope="Exact returned text for text replies; canonical SDK message JSON for non-text replies. Original HTTP bytes unavailable.")
    if grounding and status == "complete": finished["tool_events"][0]["source_evidence"] = grounding
    updated = None
    if task=="planning" and status=="complete":
        updated=history+[{"role":"user","content":[{"text":message}]},{"role":"assistant","content":[{"text":canonical(output).decode()}]}]
        if len(canonical(updated))>MAX_CONTEXT_BYTES:
            status="invalid-output"; reason="Returned turn exceeds the persisted planning-history budget; original response is retained."; updated=None
    result=database.rpc("research_finish_idea_run",dict(p_study=study_id,p_actor=actor,p_id=request_id,p_status=status,p_reason=reason,
        p_raw=raw,p_output=output,p_usage=usage,p_provenance=finished,p_messages=updated))
    return dict(run=result,session_id=session_id,analysis_version=VERSION,prompt=dict(id=prompt.id,version=prompt.version,sha256=prompt.content_sha256,text=prompt.text),
        evidence=dict(packet_id=packet_id,packet_sha256=packet["sha256"]),tool_events=provenance["read_events"],replayed=False)
