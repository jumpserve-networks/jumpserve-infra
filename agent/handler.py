import json
import logging
from uuid import UUID, uuid4
from strands import Agent
from strands.models.bedrock import BedrockModel
from database import Database
from prompt import load_active_prompt
from run_analysis import ANALYSIS_VERSION
from settings import MODEL_ID, MODEL_REGION
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _load_session(database, session_id: str) -> list[dict]:
    rows = database.get('agent_sessions', params={'id': f'eq.{session_id}', 'select': 'messages'})
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
        'p_analysis_version': ANALYSIS_VERSION, 'p_response': response_text,
    })


def _error(status, message):
    return {'statusCode': status, 'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': message})}


def lambda_handler(event, context):
    """Lambda handler for the agent — non-streaming for simplicity."""
    # Parse request
    try:
        body = json.loads(event.get("body", "{}"))
        if not isinstance(body, dict):
            raise ValueError('Expected object')
        session_id = str(UUID(body['session_id'])) if body.get('session_id') else str(uuid4())
    except (ValueError, TypeError, AttributeError):
        return _error(400, 'Invalid request or session ID')
    message = body.get("message", "")
    user_id = body.get("user_id", "anonymous")

    if not isinstance(message, str) or not message.strip():
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "message is required"}),
        }

    # Select a complete, immutable prompt snapshot before making any model call.
    try:
        database = Database()
        prompt = load_active_prompt(database)
        history = _load_session(database, session_id)
    except Exception as exc:
        logger.error('Agent context unavailable (%s)', type(exc).__name__)
        return _error(503, 'AI context is temporarily unavailable. Please try again.')

    # Create the agent
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=MODEL_REGION,
    )

    agent = Agent(
        model=model,
        system_prompt=prompt.text,
        tools=ALL_TOOLS,
    )

    # Load history into the agent
    if history:
        agent.messages = history

    # Run the agent
    result = agent(message)
    response_text = str(result)

    answer_id = str(uuid4())
    try:
        _save_turn(database, session_id, user_id, agent.messages, prompt, response_text, answer_id)
    except Exception as exc:
        logger.error('Agent answer persistence failed (%s)', type(exc).__name__)
        return _error(503, 'The AI answer could not be saved. Please try again.')

    # Collect tool events from the result
    tool_events = []
    for msg in agent.messages:
        if msg.get("role") == "assistant" and msg.get("content"):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_events.append({
                        "name": block.get("name"),
                        "input": block.get("input"),
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
        }),
    }
