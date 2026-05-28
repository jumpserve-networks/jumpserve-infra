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


def _save_session(session_id: str, messages: list[dict], user_id: str) -> None:
    """Save conversation history to Supabase (upsert)."""
    key = _get_supabase_key()
    # Try update first
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/agent_sessions?id=eq.{session_id}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"messages": messages, "updated_at": "now()"},
        timeout=10,
    )
    # If no rows updated, insert
    if resp.status_code == 200:
        # Check if we actually updated anything by trying a GET
        check = httpx.get(
            f"{SUPABASE_URL}/rest/v1/agent_sessions?id=eq.{session_id}&select=id",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if not check.json():
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/agent_sessions",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={
                    "id": session_id,
                    "user_id": user_id,
                    "messages": messages,
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
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS",
            },
            "body": json.dumps({"error": "message is required"}),
        }

    # Handle CORS preflight
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS",
            },
            "body": "",
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
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps({
            "response": response_text,
            "tool_events": tool_events,
            "session_id": session_id,
        }),
    }
