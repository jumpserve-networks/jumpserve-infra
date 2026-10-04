import json
import logging
from uuid import UUID, uuid4
from strands import Agent
from strands.models.bedrock import BedrockModel
from database import Database
from auth import authenticate, AuthError
from prompt import load_active_prompt
from run_analysis import ANALYSIS_VERSION
from settings import MODEL_ID, MODEL_REGION, MODEL_TEMPERATURE, model_id_for_module
from tools import MODULE_TOOLS
from modules import CHAT_MODULES, EMULATED_MODULE, REAL_WORLD_MODULE, REAL_WORLD_ANALYSIS_VERSION, LEO_MODULE, LEO_ANALYSIS_VERSION, HTTP2_MODULE, HTTP2_ANALYSIS_VERSION
from http2_context import prepare_http2_context
from http2_answers import HTTP2AnswerPlan, render_http2_answer, save_rendered_message, VERSION as HTTP2_RENDERER_VERSION

logger = logging.getLogger(__name__)

def _http2_evidence():
    from tools.http2_study import get_http2_study_results
    return get_http2_study_results()

def _render_http2_evidence(plan,evidence):
    from tools.http2_study import get_http2_literature, get_http2_configuration
    return render_http2_answer(plan,evidence,get_http2_literature,get_http2_configuration)


def _load_session(database, session_id: str, user_id: str, module_id=EMULATED_MODULE) -> list[dict]:
    rows = database.get('agent_sessions', params={'id': f'eq.{session_id}', 'select': 'messages,user_id,module_id'})
    if rows and rows[0].get('user_id') != user_id:
        raise AuthError(403, 'This conversation belongs to another user.')
    if rows and rows[0].get('module_id', EMULATED_MODULE) != module_id:
        raise AuthError(409, 'This conversation belongs to another test module. Start a new chat.')
    return rows[0].get('messages', []) if rows else []


def _serialize_messages(messages: list) -> list[dict]:
    """Ensure messages are JSON-serializable plain dicts."""
    serialized = []
    for msg in messages:
        m = dict(msg) if not isinstance(msg, dict) else msg
        if "content" in m and isinstance(m["content"], list):
            clean_content = []
            for block in m["content"]:
                if isinstance(block, dict):
                    clean_content.append(block)
                elif isinstance(block, str):
                    clean_content.append({"type": "text", "text": block})
                else:
                    clean_content.append({"type": "text", "text": str(block)})
            m["content"] = clean_content
        serialized.append(m)
    return serialized


def _usage(result,module_id):
    tokens=getattr(getattr(result,'metrics',None),'accumulated_usage',None)
    if not isinstance(tokens,dict):return None,None,None
    price=(5.5,27.5) if 'opus-4-6' in model_id_for_module(module_id) else (3.3,16.5)
    valid=all(isinstance(tokens.get(k),int) and not isinstance(tokens[k],bool) and tokens[k]>=0 for k in ('inputTokens','outputTokens'))
    estimate=(tokens['inputTokens']*price[0]+tokens['outputTokens']*price[1])/1e6 if valid else None
    provenance={'source':'https://www-cdn.anthropic.com/files/4zrzovbb/website/3684c2faafb97418665782cea0001f439f74b1d2.pdf','price_date':'2026-05-27','input_usd_per_million':price[0],'output_usd_per_million':price[1],'scope':'standard geo cross-region estimate; not reconciled billing'}
    return tokens,estimate,provenance

def _save_turn(database, session_id, user_id, messages, prompt, response_text, answer_id, usage=(None,None,None), answer_provenance=None):
    database.rpc('save_agent_turn', {
        'p_session_id': session_id, 'p_user_id': user_id,
        'p_messages': _serialize_messages(messages), 'p_answer_id': answer_id,
        'p_prompt_version_id': prompt.id, 'p_model_id': model_id_for_module(prompt.module_id),
        'p_analysis_version': {REAL_WORLD_MODULE: REAL_WORLD_ANALYSIS_VERSION, LEO_MODULE: LEO_ANALYSIS_VERSION, HTTP2_MODULE: HTTP2_ANALYSIS_VERSION}.get(prompt.module_id, ANALYSIS_VERSION),
        'p_response': response_text, 'p_module_id': prompt.module_id,
        'p_model_usage': usage[0], 'p_estimated_model_cost_usd': usage[1], 'p_pricing_provenance': usage[2],
        'p_answer_provenance': answer_provenance,
    })


def _error(status, message):
    return {'statusCode': status, 'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': message})}


def lambda_handler(event, context):
    """Lambda handler for the agent — non-streaming for simplicity."""
    try:
        user, bearer = authenticate(event)
    except AuthError as error:
        return _error(error.status, str(error))
    user_id = user.get('email') or user['id']

    # Parse request
    try:
        body = json.loads(event.get("body", "{}"))
        if not isinstance(body, dict):
            raise ValueError('Expected object')
        session_id = str(UUID(body['session_id'])) if body.get('session_id') else str(uuid4())
    except (ValueError, TypeError, AttributeError):
        return _error(400, 'Invalid request or session ID')
    message = body.get("message", "")
    module_id = body.get('module_id', EMULATED_MODULE)
    if not isinstance(module_id, str) or module_id not in CHAT_MODULES:
        return _error(400, 'Unsupported chat module')
    if body.get('action') == 'capabilities':
        return {'statusCode': 200, 'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'modules': list(CHAT_MODULES)})}

    if not isinstance(message, str) or not message.strip():
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "message is required"}),
        }

    # Select a complete, immutable prompt snapshot before making any model call.
    try:
        database = Database()
        prompt = load_active_prompt(database, module_id)
        history = _load_session(database, session_id, user_id, module_id)
    except AuthError as error:
        return _error(error.status, str(error))
    except Exception as exc:
        logger.error('Agent context unavailable (%s)', type(exc).__name__)
        return _error(503, 'AI context is temporarily unavailable. Please try again.')

    # Create the agent
    model = BedrockModel(
        model_id=model_id_for_module(module_id),
        region_name=MODEL_REGION,
        temperature=MODEL_TEMPERATURE,
    )

    agent = Agent(
        model=model,
        system_prompt=prompt.text,
        tools=MODULE_TOOLS[module_id],
    )

    # Load history into the agent
    if history:
        agent.messages = history

    # Run the agent
    history_length = len(agent.messages)
    answer_provenance=None
    if module_id==HTTP2_MODULE:
        try:
            evidence=_http2_evidence()
            prepare_http2_context(agent,message,evidence)
        except Exception:
            return _error(503,'Study evidence is temporarily unavailable. Please try again.')
        try:
            result = agent(authorization=bearer,structured_output_model=HTTP2AnswerPlan)
        except Exception as exc:
            failure='AI service is temporarily unavailable. Please try again.'
            save_rendered_message(agent,failure,history_length)
            try:
                _save_turn(database,session_id,user_id,agent.messages,prompt,failure,str(uuid4()),
                           answer_provenance={'renderer_version':HTTP2_RENDERER_VERSION,'status':'failed','reason':type(exc).__name__})
            except Exception:
                logger.error('Failed model request could not be persisted')
            return _error(503,failure)
        try:
            plan=HTTP2AnswerPlan.model_validate(result.structured_output)
            response_text=_render_http2_evidence(plan,evidence)
            save_rendered_message(agent,response_text,history_length)
            answer_provenance={'renderer_version':HTTP2_RENDERER_VERSION,'plan':plan.model_dump()}
        except Exception as exc:
            # Preserve a billed but unrenderable generation as a failed answer,
            # with owner/module isolation and no incidental prose displayed.
            failure='Study evidence could not be rendered. Please try again.'
            save_rendered_message(agent,failure,history_length)
            try:
                _save_turn(database,session_id,user_id,agent.messages,prompt,failure,str(uuid4()),_usage(result,module_id),
                           {'renderer_version':HTTP2_RENDERER_VERSION,'status':'failed','reason':type(exc).__name__})
            except Exception:
                logger.error('Failed rendered generation could not be persisted')
            return _error(503,'Study evidence could not be rendered. Please try again.')
    else:
        result = agent(message, authorization=bearer)
        response_text = str(result)

    answer_id = str(uuid4())
    usage = _usage(result,module_id)
    try:
        _save_turn(database, session_id, user_id, agent.messages, prompt, response_text, answer_id,usage,answer_provenance)
    except Exception as exc:
        logger.error('Agent answer persistence failed (%s)', type(exc).__name__)
        return _error(503, 'The AI answer could not be saved. Please try again.')

    # Collect tool events from the result
    tool_events = []
    for msg in agent.messages[history_length:]:
        if msg.get("role") == "assistant" and msg.get("content"):
            for block in msg["content"]:
                if not isinstance(block, dict):
                    continue
                call = block.get('toolUse') or (block if block.get('type') == 'tool_use' else None)
                if isinstance(call, dict) and isinstance(call.get('name'), str):
                    tool_events.append({
                        "name": call['name'],
                        "input": call.get("input"),
                    })

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "response": response_text,
            "tool_events": tool_events,
            "session_id": session_id,
            "answer_id": answer_id,
            "prompt_version_id": prompt.id,
            "prompt_version": prompt.version,
            "prompt_content_sha256": prompt.content_sha256,
            "analysis_version": {REAL_WORLD_MODULE: REAL_WORLD_ANALYSIS_VERSION, LEO_MODULE: LEO_ANALYSIS_VERSION, HTTP2_MODULE: HTTP2_ANALYSIS_VERSION}.get(module_id, ANALYSIS_VERSION),
            "module_id": module_id,
            "model_id": model_id_for_module(module_id),
            "model_usage": usage[0], "estimated_model_cost_usd": usage[1],
            "answer_provenance": answer_provenance,
        }),
    }
