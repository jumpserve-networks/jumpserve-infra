"""Source-preserving review rendering; model judgments never rewrite declarations."""
import hashlib
import json

VERSION = "idea-review-sources-v2"
CHANNEL = "submit_idea_issues"
PROMPT_VERSION = "research-ideas-v11"
TOP = ("problem", "question", "hypothesis", "conditions", "related_work", "alternatives",
       "design", "metrics", "controls", "falsification", "inputs", "limitations", "protocol")
METHODS = ("questions", "hypotheses", "metrics", "configurations", "input_versions",
           "dates_or_epochs", "algorithms", "seeds", "controls", "sensitivity", "replication_unit",
           "planned_units", "sample_size_rationale", "exclusions", "missing_data", "statistics",
           "dependence", "resource_limits", "stopping_rule", "prior_exposure", "coverage_limits", "data_origin")
RECONSTRUCTION = ("question", "hypothesis", "conditions", "metrics", "design", "falsification")
# These are cautious issue classifications, not assertions about what a field says.
ISSUES = {
    "unit-conflict": ("Potential mismatch in metric units or decision thresholds.", "Which unit and threshold representation should govern these declarations?"),
    "dependence": ("Potential dependence or replication problem.", "How should these declarations handle the replication unit, related observations and uncertainty?"),
    "missing-inputs": ("Required experiment inputs need clarification.", "Which required inputs are available, and how will unavailable inputs be resolved?"),
    "missing-protocol": ("A candidate protocol is not recorded.", "Can you record the candidate protocol before requesting execution readiness?"),
    "unsupported-claim": ("A claim may exceed the documented evidence or scope.", "How should these claims be limited to the evidence and declared experimental scope?"),
    "inconsistent-plan": ("These plan declarations may be inconsistent.", "Which declaration should govern, and how will these fields be reconciled?"),
    "design-gap": ("The experimental design needs clarification.", "How will the comparison and controls in these fields be made explicit?"),
    "untrusted-instruction": ("An embedded instruction was flagged as untrusted research data; no action was executed.", "Can you revise this plan field as research content while preserving its original version?"),
    "clarification": ("This part of the plan needs clarification.", "What should these fields specify before execution readiness is reviewed?"),
    "limitation": ("Declared scope or evidence limitation; this does not by itself block the scoped plan.", None),
}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def fields(packet):
    result = {"/"+key: packet[key] for key in TOP if key in packet}
    protocol = packet.get("protocol")
    if isinstance(protocol, dict):
        result.update({"/protocol/"+key: protocol[key] for key in METHODS if key in protocol})
    return result

def response_channel():
    schema = dict(type="object", additionalProperties=False, required=["issues"], properties=dict(
        issues=dict(type="array", maxItems=8, items=dict(type="object", additionalProperties=False,
            required=["code", "severity", "references"], properties=dict(code=dict(type="string", enum=list(ISSUES)), severity=dict(type="string", enum=["blocking", "warning"]),
                references=dict(type="array", minItems=1, maxItems=6, uniqueItems=True,
                    items=dict(type="string", enum=["/"+key for key in TOP]+["/protocol/"+key for key in METHODS])))))))
    return dict(tools=[dict(toolSpec=dict(name=CHANNEL, description="Classify review issues and cite packet fields. Formatting only; no actions or source paraphrases.",
        inputSchema=dict(json=schema)))], toolChoice=dict(tool=dict(name=CHANNEL)))

def parse(response, packet, task, packet_sha256):
    blocks = response["output"]["message"]["content"]
    if response.get("stopReason") != "tool_use" or len(blocks) != 1 or set(blocks[0]) != {"toolUse"}:
        raise ValueError("Expected exactly one source-referenced review")
    tool = blocks[0]["toolUse"]
    value = tool.get("input")
    if tool.get("name") != CHANNEL or not isinstance(value, dict) or set(value) != {"issues"}:
        raise ValueError("Unexpected source review schema")
    if not isinstance(value["issues"], list) or len(value["issues"]) > 8:
        raise ValueError("Invalid source review issue budget")
    available = fields(packet); seen = set(); references = []
    findings = []; questions = []
    for issue in value["issues"]:
        if not isinstance(issue, dict) or set(issue) != {"code", "severity", "references"} or not isinstance(issue.get("code"), str) or issue["code"] not in ISSUES or issue["severity"] not in ("blocking", "warning"):
            raise ValueError("Unknown review classification or model-authored prose")
        refs = issue["references"]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 6 or any(not isinstance(ref, str) or ref not in available for ref in refs) or len(set(refs)) != len(refs):
            raise ValueError("Review cites an unknown, absent or duplicate source field")
        identity = (issue["code"], tuple(sorted(refs)))
        if identity in seen: raise ValueError("Duplicate source review issue")
        seen.add(identity)
        if issue["code"] == "missing-protocol" and (refs != ["/protocol"] or available["/protocol"] is not None):
            raise ValueError("A missing-protocol judgment contradicts the recorded protocol")
        message, question = ISSUES[issue["code"]]
        if issue["code"] == "limitation" and issue["severity"] != "warning":
            raise ValueError("A scope limitation is a warning, not a fabricated blocker")
        if issue["severity"] == "warning":
            message = "AI notes a scope or evidence limitation in these declarations; assess it within the stated experimental scope."
            question = None
        suffix = " Recorded fields: " + ", ".join(refs) + "."
        field = refs[0].removeprefix("/protocol/").removeprefix("/")
        findings.append(dict(severity=issue["severity"], field=field, message=message+suffix))
        if question: questions.append(question+suffix)
        references.extend(refs)
    if task == "comprehension": references.extend("/"+key for key in RECONSTRUCTION)
    evidence = []
    for ref in dict.fromkeys(references):
        present = ref in available
        row = dict(path=ref, present=present, origin="recorded-packet", value_sha256=hashlib.sha256(canonical(available[ref])).hexdigest() if present else None, value_hash_encoding="canonical-json")
        if present:
            source = available[ref]
            row.update(value=source, state="null" if source is None else "empty" if source == "" or source == [] or source == {} else "recorded")
        else: row["state"] = "missing"
        evidence.append(row)
    verdict = "needs-clarification" if questions else "ready"
    summary = ("AI review flagged issues in the cited plan fields." if questions else "AI review found no blocking issues within the recorded plan's declared scope.")
    summary += " Source declarations below are copied by the server from this exact saved packet, not paraphrased by the model. Issue classifications remain AI judgments; scientific validity and execution approval are separate."
    output = dict(summary=summary, questions=questions, findings=findings, verdict=verdict)
    grounding = dict(version=VERSION, task=task, issues=value["issues"], fields=evidence,
        packet_sha256=packet_sha256, renderer="server", model_prose=False)
    return output, grounding
