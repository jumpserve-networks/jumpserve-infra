"""Study-scoped planning and genuinely fresh, bounded packet reviews.

The authenticated dispatcher selects this path; source strings are untrusted
data. The sole structured response channel is never executed as an action.
"""
import hashlib
import json
import time
from uuid import UUID
from auth import AuthError
from prompt import load_active_prompt
from settings import MODEL_ID, MODEL_REGION

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

def invoke_model(system, messages):
    import boto3
    from botocore.config import Config
    client = boto3.client("bedrock-runtime", region_name=MODEL_REGION,
        config=Config(connect_timeout=5, read_timeout=55, retries={"total_max_attempts":1,"mode":"standard"}))
    return client.converse(modelId=MODEL_ID, system=[{"text":system}], messages=messages,
        inferenceConfig={"maxTokens":MAX_OUTPUT_TOKENS,"temperature":0}, toolConfig=response_channel())

def owner(database, study_id, actor):
    if database.url != "https://regphejnlvfpyokpniny.supabase.co": raise AuthError(503,"Idea research target is misconfigured.")
    rows = database.get("research_study_owners", {"study_id":"eq."+study_id,"owner_id":"eq."+actor,"select":"study_id","limit":1})
    studies = database.get("research_studies", {"id":"eq."+study_id,"select":"id,study_kind","limit":1}) if rows else []
    if not studies or studies[0]["study_kind"] != "idea": raise AuthError(404,"Idea study not found.")

def handle(body, user, database, invoke=invoke_model):
    allowed = {"action","request_id","study_id","packet_id","task","session_id","message"}
    if set(body)-allowed: raise ValueError("Unsupported idea model request; prompts, history and tools are selected by the server.")
    study_id, packet_id, request_id = (uid(body.get(key)) for key in ("study_id","packet_id","request_id"))
    actor = uid(user["id"])
    task = body.get("task")
    if task not in TASKS: raise ValueError("Choose planning, comprehension or critic.")
    session_id = uid(body.get("session_id")) if body.get("session_id") else None
    message = body.get("message", "")
    if task == "planning":
        if not session_id or not isinstance(message,str) or not 1 <= len(message.strip()) <= 4000: raise ValueError("Planning needs a session and a question of up to 4000 characters.")
    elif session_id is not None or message: raise ValueError("Fresh reviews reject conversation history and extra instructions.")
    owner(database, study_id, actor)
    packets = database.get("research_idea_packets", {"id":"eq."+packet_id,"study_id":"eq."+study_id,"select":"id,version,document,raw_document,sha256","limit":1})
    if len(packets)!=1: raise AuthError(404,"Idea packet not found.")
    packet = packets[0]
    if sha(packet["raw_document"].encode())!=packet["sha256"] or json.loads(packet["raw_document"])!=packet["document"]: raise ValueError("Idea packet hash mismatch")
    history = []
    user_id = user.get("email") or actor
    if session_id:
        registered = database.get("research_idea_sessions", {"session_id":"eq."+session_id,"select":"study_id,actor_id,user_id","limit":1})
        metadata = database.get("agent_sessions", {"id":"eq."+session_id,"select":"id,user_id,module_id","limit":1})
        if metadata and (not registered or registered[0]["study_id"]!=study_id or registered[0]["actor_id"]!=actor or metadata[0]["user_id"]!=user_id or metadata[0]["module_id"]!=MODULE):
            raise AuthError(409,"Planning conversation belongs to another user, study or module.")
        if registered:
            history = database.get("agent_sessions", {"id":"eq."+session_id,"select":"messages","limit":1})[0]["messages"]
        if not isinstance(history,list) or len(history)>22: raise ValueError("Planning history exceeds its turn budget; preserve your brief and start a new session.")
    prompt = load_active_prompt(database, MODULE)
    context = dict(task=task, packet_id=packet_id, packet_version=packet["version"], packet_sha256=packet["sha256"], packet=packet["document"], user_message=message)
    messages = history + [{"role":"user","content":[{"text":canonical(context).decode()}]}]
    if len(canonical(messages))>MAX_CONTEXT_BYTES: raise ValueError("Idea context exceeds 24 KB; save a concise brief and start a new planning session.")
    provenance = dict(analysis_version=VERSION, task=task, packet_sha256=packet["sha256"], prompt_sha256=prompt.content_sha256,
        context_policy="bounded-planning-history" if task=="planning" else "fresh-packet-only", history_messages=len(history),
        context_sha256=sha(canonical(messages)), context_messages=messages, max_output_tokens=MAX_OUTPUT_TOKENS, automatic_retries=0,
        reviewer=dict(identity=MODEL_ID,type="AI",independence="Separate model invocation; shared model and packet, independent scientific review not asserted"),
        read_events=[dict(name="read_owner_idea_packet",packet_id=packet_id,study_id=study_id)], original_response_scope="Exact returned model text, not original HTTP response bytes")
    attempt = database.rpc("research_begin_idea_run", dict(p_study=study_id,p_actor=actor,p_user=user_id,p_id=request_id,p_packet=packet_id,p_task=task,
        p_session=session_id,p_prompt=prompt.id,p_model=MODEL_ID,p_request=body,p_provenance=provenance))
    if attempt.get("replayed"): return dict(run=attempt,replayed=True,analysis_version=VERSION)
    started=time.monotonic(); raw=None; output=None; status="failed"; reason=None; tokens=None; stop=None; provider_message=None
    try:
        response=invoke(prompt.text+"\n\nTrusted task selected by the backend: "+task+". Submit exactly one structured review through submit_idea_review.", messages)
        tokens=response.get("usage"); stop=response.get("stopReason")
        provider_message=response["output"]["message"]
        raw=canonical(provider_message).decode()
        blocks=provider_message["content"]
        if blocks and all(set(block)=={"text"} for block in blocks):
            raw="".join(block["text"] for block in blocks)
        output=parse_response(response,task); status="complete"
    except (ValueError,KeyError,TypeError,json.JSONDecodeError) as error:
        status="invalid-output"; reason=str(error)
    except Exception as error:
        status="failed"; reason="Model call failed ("+type(error).__name__+"). No automatic retry; retain this attempt and explicitly request a follow-up if appropriate."
    usage=dict(tokens=tokens,wall_seconds=time.monotonic()-started,measured_charges_usd=None,estimated_model_cost_usd=None,
        cost_basis="Provider usage retained when available; billing and orchestration charges unallocated, not zero.")
    finished=dict(stop_reason=stop,tool_events=[dict(name=RESPONSE_CHANNEL,executed=False,role="response-formatting")] if status=="complete" else [],data_origin="model-output",provider_message=provider_message,
        raw_response_scope="Exact returned text for text replies; canonical SDK message JSON for non-text replies. Original HTTP bytes unavailable.")
    updated = None
    if task=="planning" and status=="complete":
        updated=history+[{"role":"user","content":[{"text":message}]},{"role":"assistant","content":[{"text":canonical(output).decode()}]}]
        if len(canonical(updated))>MAX_CONTEXT_BYTES:
            status="invalid-output"; reason="Returned turn exceeds the persisted planning-history budget; original response is retained."; updated=None
    result=database.rpc("research_finish_idea_run",dict(p_study=study_id,p_actor=actor,p_id=request_id,p_status=status,p_reason=reason,
        p_raw=raw,p_output=output,p_usage=usage,p_provenance=finished,p_messages=updated))
    return dict(run=result,session_id=session_id,analysis_version=VERSION,prompt=dict(id=prompt.id,version=prompt.version,sha256=prompt.content_sha256,text=prompt.text),
        evidence=dict(packet_id=packet_id,packet_sha256=packet["sha256"]),tool_events=provenance["read_events"],replayed=False)
