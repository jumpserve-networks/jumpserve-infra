import json
import logging
from uuid import UUID, uuid4
from strands import Agent
from strands.models.bedrock import BedrockModel
from database import Database
from auth import authenticate, AuthError
from prompt import load_active_prompt
from run_analysis import ANALYSIS_VERSION
from settings import MODEL_ID, MODEL_REGION, MODEL_TEMPERATURE
from tools import MODULE_TOOLS
from modules import CHAT_MODULES, EMULATED_MODULE, REAL_WORLD_MODULE, REAL_WORLD_ANALYSIS_VERSION

logger = logging.getLogger(__name__)


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


def _save_turn(database, session_id, user_id, messages, prompt, response_text, answer_id):
    database.rpc('save_agent_turn', {
        'p_session_id': session_id, 'p_user_id': user_id,
        'p_messages': _serialize_messages(messages), 'p_answer_id': answer_id,
        'p_prompt_version_id': prompt.id, 'p_model_id': MODEL_ID,
        'p_analysis_version': REAL_WORLD_ANALYSIS_VERSION if prompt.module_id == REAL_WORLD_MODULE else ANALYSIS_VERSION,
        'p_response': response_text, 'p_module_id': prompt.module_id,
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
        model_id=MODEL_ID,
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
    result = agent(message, authorization=bearer)
    response_text = str(result)

    answer_id = str(uuid4())
    try:
        _save_turn(database, session_id, user_id, agent.messages, prompt, response_text, answer_id)
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
            "module_id": module_id,
        }),
    }
