"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Textarea } from "@/app/components/ui/textarea";
import { researchRequest } from "@/lib/research-workflow-api";
import { validateSnapshot, recordText, type ResearchSnapshot, type ResearchStudy } from "@/lib/research-workflow";
import { RESEARCH_WORKFLOW_MODULE_PATH as PATH } from "@/lib/test-modules";
import { researchModulePath, researchStudyKind, researchWorkspacePath, studiesForPathway, type ResearchStudyKind } from "@/lib/research-pathways";
import { ResearchSelect } from "@/app/components/research-workflow/select";
import { StudyPanel, type StudyView } from "@/app/components/research-workflow/study-panel";
import { ClaimQueue } from "@/app/components/research-workflow/claim-queue";
import { StudyPreparation } from "@/app/components/research-workflow/preparation";
import { PaperPreparation } from "@/app/components/research-workflow/paper-preparation";
import { Checkbox } from "@/app/components/ui/checkbox";
import { prepareAndQueue, validatePreparation } from "@/lib/research-preparation";

const REVIEWER = { identity: "Authenticated study contributor", type: "human", independence: "Study contributor; independent review not asserted" };
const NULLABLE = new Set(["source_url", "retrieved_url", "retrieved_version", "sha256", "byte_count", "supersedes_id", "amendment_reason", "followup_of", "campaign_id", "assessment_id", "estimated_cost_usd"]);
const CHOICES: Record<string, string[]> = {
  claim_type: ["numerical", "algorithm", "association", "causal", "generalization", "operational", "theory", "standard"],
  access_status: ["not-retrieved", "retrieved", "unavailable"], review_status: ["retrieved-unreviewed", "partial-review", "complete-review", "unavailable-full-text"],
  stage: ["pilot", "main", "follow-up", "retrospective-import"], experiment_type: ["reanalysis", "author-implementation", "independent-check", "new-measurement", "broader-validation", "source-review"],
  applicability: ["applicable", "inapplicable"], label: ["untested", "inconclusive", "reproduced", "discrepant"],
};
const NAMES: Record<string, string> = { source_id: "Source", claim_id: "Claim", protocol_id: "Frozen protocol", campaign_id: "Campaign", assessment_id: "Assessment", followup_of: "Follow-up of campaign", supersedes_id: "Previous version", sha256: "Original-byte SHA256", estimated_cost_usd: "Estimated cost (USD)", input_versions: "Exact input versions and hashes", requested_resources: "Requested resources", claim_type: "Kind of claim", label: "Assessment label", tested_conditions: "Tested conditions", evidence: "Evidence references", judgments: "Review judgments and check results" };
function label(name: string) { return NAMES[name] ?? name.replaceAll("_", " ").replace(/^./, c => c.toUpperCase()); }
function errorText(error: unknown) { return error instanceof Error ? error.message : "The operation could not complete. Your input is retained."; }
function templates(snapshot: ResearchSnapshot): Record<string, Record<string, unknown>> {
  const first = (name: keyof ResearchSnapshot["records"]) => snapshot.records[name][0]?.id ?? "";
  return {
    sources: { citation: "", source_url: "", retrieved_url: null, kind: "research", role: "Direct reference", retrieved_version: null, sha256: null, byte_count: null, access_status: "not-retrieved", review_status: "unavailable-full-text", review_definition: "Complete review requires substantive examination of the entire retrieved source, including sections, figures, tables, appendices and available supplements, with notes and explicit omissions.", examined: "None", unexamined: "All substantive content", retrieval_attempts: [], reviewer: REVIEWER, findings: "No findings recorded", limitations: "Source retrieval and substantive review are pending." },
    claims: { source_id: first("sources"), location: "", description: "", claim_type: "numerical", scope: { population: "", conditions: "", dates_or_epochs: "" }, metrics: [], priority: 3 },
    configurations: { identity: "", details: {}, input_versions: [], requested_resources: {} },
    campaigns: { protocol_id: first("protocols"), followup_of: null, title: "", stage: "main", experiment_type: "reanalysis", adapter: "matched-numeric-v1", planned_units: 1, coverage_limits: "Numerical agreement within the supplied cells; broader validity remains uncovered." },
    claim_checks: { claim_id: first("claims"), campaign_id: first("campaigns"), method: "", applicability: "applicable", rationale: "" },
    assessments: { claim_id: first("claims"), campaign_id: null, supersedes_id: null, label: "untested", tested_conditions: {}, evidence: [], justification: "No adequate check has been completed.", limitations: "", reviewer: REVIEWER },
    gaps: { claim_id: first("claims"), assessment_id: null, supersedes_id: null, status: "open", reason: "", next_check: "", required_inputs: [], dependencies: [], feasibility: "", estimated_cost_usd: null, cost_basis: "Not estimated; missing cost is not zero.", decision_rule: "", stopping_rule: "", priority: 3, campaign_id: null },
    reviews: { scope: "scientific", status: "conditional", reviewer: REVIEWER, judgments: { scope_and_limits_reviewed: false, release_blockers: { database: false, backend: false, frontend: false, provenance: false, access_control: false }, conditional_verification_gaps: [] }, limitations: "" },
  };
}

export function PaperIntake() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [prepare, setPrepare] = useState(true);
  const [progress, setProgress] = useState("");
  const [savedStudy, setSavedStudy] = useState<string | null>(null);
  const request = useRef("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    if (!request.current) request.current = crypto.randomUUID();
    try {
      const study = await researchRequest<ResearchStudy>("/studies", { method: "POST", body: JSON.stringify({ request_id: request.current, paper: { title: data.get("title"), paper_url: data.get("paper_url"), domain: data.get("domain"), scope: data.get("scope"), origin_module: null } }) });
      setSavedStudy(study.id);
      if (prepare) {
        setProgress("Checking available preparation plans…");
        const status = validatePreparation(await researchRequest(`/studies/${study.id}/prepare`));
        if (status.available_plan) await prepareAndQueue(study.id, request.current, setProgress, researchRequest);
      }
      router.push(`${PATH}/workspace/${study.id}`);
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="max-w-3xl space-y-4 rounded-lg border p-5">{[["title", "Paper title", "text"], ["paper_url", "Paper URL or DOI URL", "url"], ["domain", "Research domain", "text"]].map(([name, text, type]) => <label key={name} className="block space-y-2 text-sm"><span className="font-medium">{text}</span><Input required type={type} name={name} maxLength={name === "title" ? 300 : 5000} disabled={busy || savedStudy !== null} /></label>)}<label className="block space-y-2 text-sm"><span className="font-medium">Reproduction scope</span><Textarea name="scope" required maxLength={5000} disabled={busy || savedStudy !== null} placeholder="Which claims, populations, inputs and conditions will the assessment cover?" /></label><label className="flex items-start gap-2 text-sm"><Checkbox checked={prepare} disabled={busy || savedStudy !== null} onCheckedChange={value => setPrepare(Boolean(value))} /><span>Prepare available checks and queue them after saving the study. Earlier evidence keeps its original scope; claim review remains separate.</span></label>{progress ? <p role="status" className="text-sm">{progress}</p> : null}{error ? <p role="alert" className="text-sm text-destructive">{error} {savedStudy ? "The study was saved; resume preparation from its workspace." : ""}</p> : null}{savedStudy ? <Link className="block text-sm underline" href={`${PATH}/workspace/${savedStudy}`}>Open saved study and resume preparation</Link> : <Button disabled={busy} type="submit">{busy ? "Saving and preparing…" : prepare ? "Create study and prepare checks" : "Create private study draft"}</Button>}</form>;
}

export function OwnerStudies({ kind = "paper" }: { kind?: ResearchStudyKind }) {
  const [result, setResult] = useState<{ studies: ResearchStudy[] } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    researchRequest<{ studies: ResearchStudy[] }>("/studies?mine=1", { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setResult(value); }).catch(failure => { if (!controller.signal.aborted) setError(errorText(failure)); });
    return () => controller.abort();
  }, []);
  const studies = studiesForPathway(result?.studies ?? [], kind);
  return <section className="space-y-4">{error ? <p role="alert" className="rounded-lg border p-4 text-sm text-destructive">{error}</p> : !result ? <p role="status">Loading your {kind === "idea" ? "ideas" : "paper studies"}…</p> : studies.length === 0 ? <p className="rounded-lg border p-4 text-sm">You have no {kind === "idea" ? "idea" : "paper study"} drafts yet. <Link className="underline" href={`${researchModulePath(kind)}/${kind === "idea" ? "new-idea" : "new-study"}`}>{kind === "idea" ? "Develop an idea" : "Assess a paper"}</Link>.</p> : studies.map(study => <article key={study.id} className="space-y-2 rounded-lg border p-4"><h2 className="font-semibold"><Link className="underline" href={researchWorkspacePath(study)}>{study.title}</Link></h2><p className="text-xs text-muted-foreground">{kind === "idea" ? "Unpublished research idea" : "Paper assessment"}</p><p className="text-sm text-muted-foreground">{study.domain} · {study.scope}</p></article>)}</section>;
}

function RecordEditor({ snapshot, onSaved }: { snapshot: ResearchSnapshot; onSaved: () => Promise<void> }) {
  const available = templates(snapshot);
  const [kind, setKind] = useState("sources");
  const [values, setValues] = useState<Record<string, unknown>>(available.sources);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const request = useRef("");
  function change(name: string, value: unknown) { request.current = ""; setValues(prior => ({ ...prior, [name]: value })); }
  function relation(name: string) {
    const maps: Record<string, keyof ResearchSnapshot["records"]> = { source_id: "sources", claim_id: "claims", protocol_id: "protocols", campaign_id: "campaigns", assessment_id: "assessments", followup_of: "campaigns" };
    return name === "supersedes_id" ? snapshot.records[kind as "assessments" | "gaps"] : maps[name] ? snapshot.records[maps[name]] : null;
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    if (!request.current) request.current = crypto.randomUUID();
    try {
      const row: Record<string, unknown> = { id: request.current };
      for (const [name, initial] of Object.entries(available[kind])) {
        const value = values[name];
        if (value === "" && NULLABLE.has(name)) row[name] = null;
        else if (typeof initial === "number" || name === "estimated_cost_usd" || name === "byte_count") row[name] = value === null ? null : Number(value);
        else if (initial !== null && typeof initial === "object") row[name] = typeof value === "string" ? JSON.parse(value) : value;
        else row[name] = value;
      }
      await researchRequest(`/studies/${snapshot.study.id}/records`, { method: "POST", body: JSON.stringify({ kind, record: row }) });
      await onSaved(); request.current = ""; setMessage("New record preserved. Earlier records remain unchanged.");
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-4"><label className="block space-y-1 text-sm"><span className="font-medium">Record to add</span><ResearchSelect label="Record to add" value={kind} onChange={value => { setKind(value); setValues(available[value]); setMessage(""); request.current = ""; }} options={Object.keys(available).map(name => ({ value: name, label: label(name) }))} /></label><p className="text-xs text-muted-foreground">Review status, human or AI identity and independence must describe the actual work. For amendments, select the previous record. JSON fields retain scientific configurations and evidence references.</p><div className="grid gap-4 md:grid-cols-2">{Object.entries(available[kind]).map(([name, initial]) => {
    const linked = relation(name);
    let choices = CHOICES[name];
    if (name === "status") choices = kind === "gaps" ? ["open", "blocked", "planned", "resolved", "stopped", "inapplicable"] : ["conditional", "passed", "failed"];
    if (name === "scope" && kind === "reviews") choices = ["scientific", "software", "model-evaluation"];
    const json = initial !== null && typeof initial === "object";
    return <label key={`${kind}:${name}`} className={`block space-y-1 text-sm ${json || name === "description" || name === "limitations" ? "md:col-span-2" : ""}`}><span className="font-medium">{label(name)}{json ? " (JSON)" : ""}</span>{linked || choices ? <ResearchSelect label={label(name)} required={!NULLABLE.has(name)} value={String(values[name] ?? "")} onChange={value => change(name, value)} options={linked ? [{ value: "", label: NULLABLE.has(name) ? "Select a record or leave unlinked" : "Select a record" }, ...linked.map(row => ({ value: row.id, label: recordText(row, "description", recordText(row, "title", recordText(row, "citation", `${row.created_at} · ${recordText(row, "label", row.id)}`))) }))] : (choices ?? []).map(value => ({ value, label: value }))} /> : json ? <Textarea className="min-h-24 font-mono text-xs" required value={typeof values[name] === "string" ? values[name] as string : JSON.stringify(values[name], null, 2)} onChange={event => change(name, event.target.value)} /> : <Input required={!NULLABLE.has(name)} type={typeof initial === "number" || name === "estimated_cost_usd" || name === "byte_count" ? "number" : "text"} step="any" value={String(values[name] ?? "")} onChange={event => change(name, event.target.value)} />}</label>;
  })}</div>{message ? <p role="status" className="text-sm">{message}</p> : null}<Button type="submit" disabled={busy}>{busy ? "Preserving record…" : "Preserve new record"}</Button></form>;
}

function ProtocolEditor({ snapshot, onSaved }: { snapshot: ResearchSnapshot; onSaved: () => Promise<void> }) {
  const [document, setDocument] = useState(JSON.stringify({ questions: [""], hypotheses: "", metrics: [{ name: "", units: "", tolerance_absolute: 0 }], configurations: [{ identity: "", details: {} }], input_versions: [{ identity: "", sha256: "" }], dates_or_epochs: "", algorithms: ["matched-numeric-v1"], seeds: { applicable: false, rationale: "Deterministic numerical census; no stochastic algorithm." }, controls: [], sensitivity: { applicable: false, rationale: "One fixed comparison criterion; changes require separate protocols." }, replication_unit: "", sample_size_rationale: "", exclusions: "", missing_data: "", statistics: "", dependence: "", resource_limits: { max_observations: 1000, max_input_bytes: 2000000, wall_seconds: 10, estimated_cost_usd: null, cost_basis: "Unallocated costs; missing charges are not zero. Replace with measured or estimated cost basis when available." }, stopping_rule: "", prior_exposure: "", coverage_limits: "" }, null, 2));
  const [previous, setPrevious] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const request = useRef("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    if (!request.current) request.current = crypto.randomUUID();
    try {
      const parent = snapshot.records.protocols.find(row => row.id === previous);
      await researchRequest(`/studies/${snapshot.study.id}/protocols`, { method: "POST", body: JSON.stringify({ request_id: request.current, document: JSON.parse(document), supersedes_id: previous || null, version: parent ? Number(parent.version) + 1 : 1, amendment_reason: previous ? reason : null }) });
      await onSaved(); request.current = ""; setMessage("Protocol frozen with a canonical document hash. Preserve amendments as new versions.");
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-4 text-sm"><p>Fill every scientific design field and disclose actual prior exposure before freezing. The built-in numerical adapter uses exact original-input hashes and descriptive comparisons. This template is incomplete until you supply the paper-specific design.</p><label className="block space-y-1"><span className="font-medium">Previous protocol, for an amendment</span><ResearchSelect label="Previous protocol" value={previous} onChange={value => { setPrevious(value); request.current = ""; }} options={[{ value: "", label: "Initial protocol" }, ...snapshot.records.protocols.map(row => ({ value: row.id, label: `Version ${String(row.version)} · ${String(row.frozen_at)}` }))]} /></label>{previous ? <label className="block space-y-1"><span className="font-medium">Amendment rationale</span><Input required value={reason} onChange={event => { setReason(event.target.value); request.current = ""; }} /></label> : null}<label className="block space-y-1"><span className="font-medium">Protocol document (JSON)</span><Textarea required className="min-h-96 font-mono text-xs" value={document} onChange={event => { setDocument(event.target.value); request.current = ""; }} /></label>{message ? <p role="status">{message}</p> : null}<Button type="submit" disabled={busy}>{busy ? "Freezing protocol…" : "Freeze protocol version"}</Button></form>;
}

function CampaignRunner({ snapshot, onSaved }: { snapshot: ResearchSnapshot; onSaved: () => Promise<void> }) {
  const [campaign, setCampaign] = useState("");
  const [input, setInput] = useState("");
  const [hash, setHash] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const request = useRef("");
  async function fingerprint(text: string) { return [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)))].map(value => value.toString(16).padStart(2, "0")).join(""); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    if (!request.current) request.current = crypto.randomUUID();
    try {
      const result = await researchRequest<{ run: { status: string; reason: string | null } }>(`/studies/${snapshot.study.id}/runs`, { method: "POST", body: JSON.stringify({ request_id: request.current, campaign_id: campaign, raw_input: input }) });
      await onSaved(); request.current = ""; setMessage(`Run preserved: ${result.run.status}. ${result.run.reason ?? "Numerical results require a claim-specific evidence review."}`);
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-4 text-sm"><p>Execute a frozen numerical campaign with matched published and observed JSON arrays. The interactive adapter is bounded to 1,000 observations and 10 seconds; other methods require a domain implementation or documented operator import.</p><label className="block space-y-1"><span className="font-medium">Campaign</span><ResearchSelect label="Campaign" required value={campaign} onChange={value => { setCampaign(value); request.current = ""; }} options={[{ value: "", label: "Select a numerical campaign" }, ...snapshot.records.campaigns.filter(row => row.adapter === "matched-numeric-v1").map(row => ({ value: row.id, label: recordText(row, "title") }))]} /></label><label className="block space-y-1"><span className="font-medium">Original UTF-8 JSON file</span><Input type="file" accept="application/json,.json" onChange={async event => { const file = event.target.files?.[0]; if (!file) return; try { if (file.size > 256000) throw new Error("File exceeds the interactive 256 KB input limit; use the operator runner."); const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer()); setInput(text); setHash(await fingerprint(text)); request.current = ""; } catch (failure) { setMessage(errorText(failure)); } }} /></label><label className="block space-y-1"><span className="font-medium">Original input text</span><Textarea required className="min-h-48 font-mono text-xs" value={input} onChange={event => { setInput(event.target.value); setHash(""); request.current = ""; }} /></label><Button type="button" size="sm" variant="outline" onClick={async () => setHash(await fingerprint(input))}>Calculate original-input SHA256</Button>{hash ? <p className="break-all text-xs">SHA256: {hash}. This exact hash must appear in the frozen protocol.</p> : null}{message ? <p role="status">{message}</p> : null}<Button type="submit" disabled={busy || !campaign}>{busy ? "Running bounded comparison…" : "Run and preserve comparison"}</Button></form>;
}

function Publication({ snapshot, onSaved }: { snapshot: ResearchSnapshot; onSaved: () => Promise<void> }) {
  const [scientific, setScientific] = useState(""); const [software, setSoftware] = useState(""); const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false); const [message, setMessage] = useState(""); const request = useRef("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); if (!request.current) request.current = crypto.randomUUID();
    try { await researchRequest(`/studies/${snapshot.study.id}/publish`, { method: "POST", body: JSON.stringify({ request_id: request.current, scientific_review_id: scientific, software_review_id: software, reason }) }); await onSaved(); request.current = ""; setMessage("A fixed snapshot is now public. Later records remain private until separately reviewed and published."); }
    catch (failure) { setMessage(errorText(failure)); } finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-4 text-sm"><p>Publish the current evidence as a fixed public snapshot. Scientific coverage may remain incomplete; each unresolved claim needs a current gap record. Passed scope and software reviews are required.</p>{[["scientific", scientific, setScientific], ["software", software, setSoftware]].map(([scope, value, setter]) => <label key={scope as string} className="block space-y-1"><span className="font-medium capitalize">{scope as string} review</span><ResearchSelect label={`${scope as string} review`} required value={value as string} onChange={value => { (setter as (value: string) => void)(value); request.current = ""; }} options={[{ value: "", label: "Select a passed review" }, ...snapshot.records.reviews.filter(row => row.scope === scope && row.status === "passed").map(row => ({ value: row.id, label: `${row.created_at} · ${recordText(row, "limitations")}` }))]} /></label>)}<label className="block space-y-1"><span className="font-medium">Publication rationale and scope</span><Textarea required value={reason} onChange={event => { setReason(event.target.value); request.current = ""; }} /></label>{message ? <p role="status">{message}</p> : null}<Button type="submit" disabled={busy}>{busy ? "Publishing snapshot…" : "Publish reviewed snapshot"}</Button></form>;
}

export function StudyWorkspace({ studyId, view, kind = "paper" }: { studyId: string; view: StudyView; kind?: ResearchStudyKind }) {
  const router = useRouter();
  const base = researchModulePath(kind);
  const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    researchRequest(`/studies/${studyId}`, { signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return;
      const validated = validateSnapshot(value);
      const actualKind = researchStudyKind(validated.study);
      if (actualKind !== kind) {
        router.replace(`${researchModulePath(actualKind)}/workspace/${studyId}?view=${view}`);
        return;
      }
      setSnapshot(validated);
    }).catch(failure => { if (!controller.signal.aborted) setError(errorText(failure)); });
    return () => controller.abort();
  }, [studyId, kind, router, view]);
  async function reload() { setSnapshot(validateSnapshot(await researchRequest(`/studies/${studyId}`))); }
  function download() {
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `research-draft-${studyId}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  if (error) return <p role="alert" className="rounded-lg border p-4 text-sm text-destructive">{error}</p>;
  if (!snapshot) return <p role="status">Loading the owner-scoped study…</p>;
  return <div className="space-y-6"><h2 className="text-xl font-semibold">{snapshot.study.title}</h2>{snapshot.study.claim_design ? <Link className="text-sm underline" href={researchWorkspacePath(snapshot.study)}>Return to experiment design and fresh reviews</Link> : null}<div className="flex flex-wrap gap-3"><Button size="sm" variant="outline" onClick={download}>Download draft JSON</Button><Link className="text-sm underline" href={`${base}/studies/${studyId}`}>View published snapshot</Link>{snapshot.study.study_kind === "idea" ? <Link className="text-sm underline" href={`${base}/ideas/${studyId}`}>Return to idea planning and fresh reviews</Link> : null}</div>{snapshot.study.study_kind === "idea" || snapshot.study.claim_design ? null : <PaperPreparation studyId={studyId} onSaved={reload} />}<StudyPreparation snapshot={snapshot} /><StudyPanel snapshot={snapshot} view={view} basePath={`${base}/workspace/${studyId}`} /><ClaimQueue snapshot={snapshot} onEvidenceChanged={reload} /><section className="space-y-4 rounded-lg border p-5"><h2 className="text-lg font-semibold">Build and preserve the study</h2>{[["research-records", "Add sources, claims, assessments and evidence gaps", <RecordEditor key="records" snapshot={snapshot} onSaved={reload} />], ["research-protocol", "Freeze a protocol or amendment", <ProtocolEditor key="protocol" snapshot={snapshot} onSaved={reload} />], ["research-runner", "Execute a bounded numerical campaign", <CampaignRunner key="runner" snapshot={snapshot} onSaved={reload} />], ["research-publication", "Publish a reviewed snapshot", <Publication key="publication" snapshot={snapshot} onSaved={reload} />]].map(([id, title, form]) => <details id={id as string} key={id as string} className="scroll-mt-24 rounded-lg border p-4"><summary className="cursor-pointer text-sm font-medium">{title}</summary><div className="mt-4">{form}</div></details>)}</section></div>;
}
