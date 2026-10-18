"""Bounded conversational planning. This response channel never executes actions."""
VERSION = "idea-interview-v1"
PROMPT_VERSION = "research-ideas-v11"
FIELDS = ("question", "problem", "hypothesis", "conditions", "design", "metrics",
    "controls", "falsification", "inputs", "related_work", "alternatives", "limitations",
    "dates_or_epochs", "algorithms", "seeds", "sensitivity", "replication_unit",
    "sample_size_rationale", "exclusions", "missing_data", "statistics", "dependence",
    "stopping_rule", "prior_exposure", "data_origin", "max_observations")
CHANNEL = "submit_idea_question"
SCHEMA = dict(type="object", additionalProperties=False, required=["summary", "question", "field"], properties=dict(
    summary=dict(type="string", minLength=1, maxLength=1600),
    question=dict(type="string", minLength=1, maxLength=1000),
    field=dict(type="string", enum=list(FIELDS))))

def system_text(prompt, interview=False, task=None):
    """Select a server-owned task template, never instructions from packet data."""
    if not getattr(prompt, "system_prompt", "").lstrip().startswith("{"):
        if interview:
            raise ValueError("Interview requires its evaluated task prompt version")
        return prompt.text
    import json
    template = json.loads(prompt.system_prompt)
    version = template.get("schema")
    keys = {"schema", "review", "interview", "planning"} if version == "idea-task-prompts-v2" else {"schema", "review", "interview"}
    if set(template) != keys or version not in ("idea-task-prompts-v1", "idea-task-prompts-v2"):
        raise ValueError("Unsupported idea task prompt schema")
    if any(not isinstance(template[key], str) or not 1 <= len(template[key]) <= 12000 for key in keys - {"schema"}):
        raise ValueError("Invalid idea task prompt bounds")
    key = "interview" if interview else "planning" if task == "planning" and "planning" in template else "review"
    return template[key] + "\n\n" + prompt.research_context

def response_channel():
    return dict(tools=[dict(toolSpec=dict(name=CHANNEL,
        description="Return one tailored planning question and the field its answer will address. Formatting only.",
        inputSchema=dict(json=SCHEMA)))], toolChoice=dict(tool=dict(name=CHANNEL)))

def parse(response, preferred_field=None):
    blocks = response["output"]["message"]["content"]
    if response.get("stopReason") != "tool_use" or len(blocks) != 1 or set(blocks[0]) != {"toolUse"}:
        raise ValueError("Expected one structured interview question")
    tool = blocks[0]["toolUse"]
    value = tool.get("input")
    if tool.get("name") != CHANNEL or not isinstance(value, dict) or set(value) != {"summary", "question", "field"}:
        raise ValueError("Unexpected interview question schema")
    if value["field"] not in FIELDS or preferred_field and value["field"] != preferred_field:
        raise ValueError("Interview question must address an allowed, requested field")
    for key, limit in (("summary", 1600), ("question", 1000)):
        if not isinstance(value[key], str) or not 1 <= len(value[key].strip()) <= limit:
            raise ValueError("Interview text exceeds its bounds")
    return value
