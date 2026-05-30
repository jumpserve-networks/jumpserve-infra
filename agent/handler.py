import json
import os
import boto3
import httpx
from strands import Agent
from strands.models.bedrock import BedrockModel
from prompt import SYSTEM_PROMPT
from tools import ALL_TOOLS

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_supabase_key: str | None = None


def _get_supabase_key() -> str:
    global _supabase_key
    if _supabase_key:
        return _supabase_key
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=os.environ["SUPABASE_SECRET_ARN"])
    _supabase_key = resp["SecretString"]
    return _supabase_key


def _load_session(session_id: str) -> list[dict]:
    """Load conversation history from Supabase."""
    key = _get_supabase_key()
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/agent_sessions?id=eq.{session_id}&select=messages",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        if data and data[0].get("messages"):
            return data[0]["messages"]
    return []


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


def _save_session(session_id: str, messages: list[dict], user_id: str) -> None:
    """Save conversation history to Supabase (upsert)."""
    key = _get_supabase_key()
    safe_messages = _serialize_messages(messages)
    httpx.post(
        f"{SUPABASE_URL}/rest/v1/agent_sessions",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json={
            "id": session_id,
            "user_id": user_id,
            "messages": safe_messages,
        },
        timeout=10,
    )


def lambda_handler(event, context):
    """Lambda handler for the agent — non-streaming for simplicity."""
    # Parse request
    body = json.loads(event.get("body", "{}"))
    message = body.get("message", "")
    session_id = body.get("session_id", "default")
    user_id = body.get("user_id", "anonymous")

    if not message:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "message is required"}),
        }

    # Load session history
    history = _load_session(session_id)

    # Create the agent
    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-6",
        region_name="us-east-1",
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
    )

    # Load history into the agent
    if history:
        agent.messages = history

    # Run the agent
    result = agent(message)
    response_text = str(result)

    # Save updated session
    _save_session(session_id, agent.messages, user_id)

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
        }),
    }
