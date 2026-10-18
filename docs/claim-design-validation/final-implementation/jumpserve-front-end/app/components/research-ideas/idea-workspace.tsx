"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Textarea } from "@/app/components/ui/textarea";
import { ResearchSelect } from "@/app/components/research-workflow/select";
import { ClaimQueue } from "@/app/components/research-workflow/claim-queue";
import { researchRequest } from "@/lib/research-workflow-api";
import { emptyIdea, IDEA_FIELDS, IDEA_VERSION, ideaReview, validateIdeaState, type IdeaDocument, type IdeaPacket, type IdeaRun, type IdeaState, type IdeaTask } from "@/lib/research-ideas";
import { ideaModelRequest } from "@/lib/research-idea-api";
import { validateSnapshot, type ResearchSnapshot, type ResearchStudy } from "@/lib/research-workflow";
import { RESEARCH_IDEAS_MODULE_PATH as PATH } from "@/lib/test-modules";
import { NetworkProtocolEditor } from "./network-protocol-editor";
import { preparedQueueRequests, type NetworkingCapabilities } from "@/lib/network-execution";
import { IdeaReviewSources } from "./idea-review-sources";
import { IdeaGuide } from "./idea-guide";

const LABELS: Record<typeof IDEA_FIELDS[number], string> = {
  problem: "Problem and motivation", question: "Research question", hypothesis: "Proposed hypothesis", conditions: "Conditions and population",
  related_work: "Related work and novelty limits", alternatives: "Alternative explanations and designs", design: "Proposed experimental comparison",
  metrics: "Measurements and units", controls: "Controls and dependence", falsification: "What would count against the hypothesis?",
  inputs: "Required inputs and availability", limitations: "Scope and limitations",
};
const errorText = (error: unknown) => error instanceof Error ? error.message : "Request failed. Preserve your input and inspect retained status.";

export function IdeaIntake() {
  const router = useRouter();
  const [title, setTitle] = useState(""); const [domain, setDomain] = useState("");
  const [question, setQuestion] = useState(""); const [hypothesis, setHypothesis] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const ids = useRef<{ study: string; packet: string } | null>(null);
  const [savedStudy, setSavedStudy] = useState<string | null>(null);
  function changed() { ids.current = null; }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    ids.current ??= { study: crypto.randomUUID(), packet: crypto.randomUUID() };
    try {
      const capabilities = await researchRequest<{ ideas?: { version: string } }>("/capabilities");
      if (capabilities.ideas?.version !== IDEA_VERSION) throw new Error("The connected research service does not yet support unpublished ideas. Your unsaved idea remains in this form.");
      const study = await researchRequest<ResearchStudy>("/studies", { method: "POST", body: JSON.stringify({ request_id: ids.current.study,
        paper: { title, domain, scope: "Unpublished research idea. No experimental evidence has been collected by this intake.", paper_url: null, study_kind: "idea", origin_module: null } }) });
      if (study.id !== ids.current.study || study.study_kind !== "idea" || study.paper_url !== null) throw new Error("Idea study identity or origin was not confirmed; inspect saved studies before creating another.");
      setSavedStudy(study.id);
      const packet = await researchRequest<IdeaPacket>(`/studies/${study.id}/idea`, { method: "POST", body: JSON.stringify({ action: "save", request_id: ids.current.packet,
        supersedes_id: null, document: { ...emptyIdea(), question, hypothesis }, reason: "Initial owner-supplied unpublished idea" }) });
      if (packet.id !== ids.current.packet || packet.study_id !== study.id) throw new Error("Initial packet persistence was not confirmed. The study draft may already exist.");
      router.push(`${PATH}/ideas/${study.id}`);
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-5 rounded-lg border p-5" aria-label="New unpublished research idea">
    <p className="text-sm text-muted-foreground">Begin with what you know. The planning discussion can help identify missing assumptions and a testable hypothesis. Your draft stays private.</p>
    {[["Idea title", title, setTitle], ["Research domain", domain, setDomain]].map(([label, value, setter]) => <label key={label as string} className="block space-y-1 text-sm"><span className="font-medium">{label as string}</span><Input required maxLength={300} disabled={busy || Boolean(savedStudy)} value={value as string} onChange={event => { (setter as (value: string) => void)(event.target.value); changed(); }} /></label>)}
    <label className="block space-y-1 text-sm"><span className="font-medium">Research question</span><Textarea className="text-foreground" required maxLength={5000} disabled={busy || Boolean(savedStudy)} value={question} onChange={event => { setQuestion(event.target.value); changed(); }} /></label>
    <label className="block space-y-1 text-sm"><span className="font-medium">Proposed hypothesis, if you have one</span><Textarea className="text-foreground" maxLength={5000} disabled={busy || Boolean(savedStudy)} value={hypothesis} onChange={event => { setHypothesis(event.target.value); changed(); }} /></label>
    {error ? <p role="alert" className="rounded-md border p-3 text-sm text-destructive">{error}</p> : null}
    <Button type="submit" disabled={busy}>{busy ? "Preserving your idea…" : "Create private idea workspace"}</Button>
    {savedStudy ? <p className="text-sm">Your study draft is preserved. <Link className="underline" href={`${PATH}/ideas/${savedStudy}`}>Resume this workspace</Link> if the initial plan save was interrupted.</p> : null}
  </form>;
}

function ModelAttempt({ run, packet }: { run: IdeaRun; packet?: IdeaPacket }) {
  return <article className="space-y-3 rounded-md border p-4 text-sm">
    <p className="font-medium capitalize">{run.task} · {run.status}{run.output ? ` · ${run.output.verdict === "ready" ? "Plan recommendation: ready" : "Clarification needed"}` : ""}</p>
    {run.reason ? <p className="text-destructive">{run.reason}</p> : null}
    {run.output ? <><p className="whitespace-pre-wrap">{run.output.summary}</p>
      {run.output.questions.length ? <ul className="list-disc space-y-1 pl-5">{run.output.questions.map((question, index) => <li key={index}>{question}</li>)}</ul> : null}
      {run.output.findings.map((finding, index) => <p key={index}><strong>{finding.severity} · {finding.field}:</strong> {finding.message}</p>)}</> : null}
    <IdeaReviewSources run={run} packet={packet} />
    <p className="text-xs text-muted-foreground">AI · {run.model_id}. {run.task === "planning" ? "Bounded planning conversation." : "Fresh packet-only context; shared model and sources, independent scientific review not asserted."}</p>
    <details><summary className="cursor-pointer text-xs">Prompt, context and usage provenance</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">{JSON.stringify({ prompt_version_id: run.prompt_version_id, packet_id: run.packet_id, provenance: run.provenance, usage: run.usage }, null, 2)}</pre></details>
  </article>;
}

export function PacketEditor({ packet, studyId, onSaved, onDirty, planningEndpoint = "idea" }: { planningEndpoint?: string; packet: IdeaPacket | null; studyId: string; onSaved: (expectedPacketId?: string) => Promise<void>; onDirty: () => void }) {
  const [document, setDocument] = useState<IdeaDocument>(packet?.document ?? emptyIdea());
  const [protocol, setProtocol] = useState(JSON.stringify(packet?.document.protocol ?? null, null, 2));
  const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const request = useRef("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); request.current ||= crypto.randomUUID();
    try {
      const value = { ...document, protocol: JSON.parse(protocol) };
      const result = await researchRequest<IdeaPacket>(`/studies/${studyId}/${planningEndpoint}`, { method: "POST", body: JSON.stringify({ action: "save", request_id: request.current, supersedes_id: packet?.id ?? null, document: value, reason }) });
      if (result.id !== request.current || result.supersedes_id !== (packet?.id ?? null)) throw new Error("New packet version was not confirmed saved.");
      await onSaved(result.id);
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={save} className="space-y-4" aria-label="Versioned idea plan">
    <p className="text-sm text-muted-foreground">Leave genuinely unknown information empty. Save changes as a new version before requesting reviews. Earlier packets and their reviews remain recorded.</p>
    <div className="grid gap-4 md:grid-cols-2">{IDEA_FIELDS.map(field => <label key={field} className="block space-y-1 text-sm"><span className="font-medium">{LABELS[field]}</span><Textarea aria-label={LABELS[field]} readOnly={planningEndpoint === "claim-design" && field === "hypothesis"} className="text-foreground" maxLength={5000} disabled={busy} value={document[field]} onChange={event => { setDocument(prior => ({ ...prior, [field]: event.target.value })); request.current = ""; onDirty(); }} /></label>)}</div>
    <details className="rounded-md border p-4"><summary className="cursor-pointer text-sm font-medium">Candidate scientific protocol</summary>
      <p className="mt-3 text-sm text-muted-foreground">Use the existing protocol fields: questions, hypotheses, metrics and units, configurations, exact input versions and hashes, dates, algorithms, seed applicability, controls, sensitivity, replication, planned_units, sample-size rationale, exclusions, missingness, statistics and dependence, resource limits, stopping rule, prior exposure and coverage limits. Drafts may use null until this is specified. Review readiness requires a complete candidate.</p>
      <label className="mt-3 block space-y-1 text-sm"><span>Candidate protocol JSON</span><Textarea aria-label="Candidate protocol JSON" className="min-h-64 font-mono text-xs text-foreground" disabled={busy} value={protocol} onChange={event => { setProtocol(event.target.value); request.current = ""; onDirty(); }} /></label>
    </details>
    <NetworkProtocolEditor studyId={studyId} document={document} protocol={protocol} onChange={value => { setProtocol(value); request.current = ""; onDirty(); }} />
    <label className="block space-y-1 text-sm"><span className="font-medium">Why this version changed</span><Input required maxLength={2000} disabled={busy} value={reason} onChange={event => { setReason(event.target.value); request.current = ""; }} /></label>
    {message ? <p role="alert" className="text-sm text-destructive">{message}</p> : null}
    <Button type="submit" disabled={busy}>{busy ? "Preserving new version…" : "Save a new plan version"}</Button>
  </form>;
}

export function IdeaActions({ state, studyId, reload, dirty, planningEndpoint = "idea" }: { planningEndpoint?: string; state: IdeaState; studyId: string; reload: () => Promise<void>; dirty: boolean }) {
  const [question, setQuestion] = useState(""); const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const session = useRef<string>([...state.runs].reverse().find(run => run.task === "planning")?.session_id ?? "");
  const requests = useRef<Record<string, string>>({});
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const comprehension = ideaReview(state, "comprehension"); const critic = ideaReview(state, "critic");
  async function review(task: IdeaTask) {
    setBusy(true); setMessage(""); requests.current[task] ||= crypto.randomUUID();
    if (task === "planning") session.current ||= crypto.randomUUID();
    controller.current = new AbortController();
    try {
      const result = await ideaModelRequest({ request_id: requests.current[task], study_id: studyId, packet_id: state.current_packet_id, task,
        ...(task === "planning" ? { session_id: session.current, message: question } : {}) }, controller.current.signal);
      await reload();
      if (result.run.status === "running") setMessage("This attempt is still unconfirmed. Refresh retained history before requesting another call.");
      else { delete requests.current[task]; setMessage(`Attempt retained: ${result.run.status}. ${result.run.reason ?? "Review its questions and findings below."}`); }
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!comprehension || !critic) return;
    setBusy(true); setMessage(""); requests.current.accept ||= crypto.randomUUID();
    try {
      await researchRequest(`/studies/${studyId}/${planningEndpoint}`, { method: "POST", body: JSON.stringify({ action: "accept", request_id: requests.current.accept,
        packet_id: state.current_packet_id, comprehension_run_id: comprehension.id, critic_run_id: critic.id, reason }) });
      await reload(); delete requests.current.accept; setMessage("Readiness recorded for this packet. Scientific findings remain separate.");
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <section className="space-y-5 rounded-lg border p-5" aria-labelledby="idea-reviews-title">
    <h2 id="idea-reviews-title" className="text-lg font-semibold">Discuss the plan and challenge it</h2>
    <p className="text-sm text-muted-foreground">AI receives the saved packet shown above. Comprehension and critic requests start fresh with no planning history or earlier verdict. A review recommendation does not establish novelty or scientific validity.</p>
    {planningEndpoint === "idea" ? <form onSubmit={event => { event.preventDefault(); void review("planning"); }} className="space-y-3">
      <label className="block space-y-1 text-sm"><span className="font-medium">Planning discussion</span><Textarea className="text-foreground" required maxLength={4000} disabled={busy} value={question} onChange={event => { setQuestion(event.target.value); delete requests.current.planning; }} placeholder="Explain the idea, answer a question, or ask the AI to challenge an assumption." /></label>
      <div className="flex flex-wrap gap-3"><Button type="submit" disabled={busy || dirty || !question.trim()}>Send planning question</Button><Button type="button" variant="outline" disabled={busy} onClick={() => { session.current = ""; delete requests.current.planning; setMessage("The next planning question starts a new conversation using the saved packet."); }}>Start a new planning conversation</Button></div>
    </form> : null}
    {dirty ? <p role="status" className="text-sm">Save the changed plan as a new version before further AI requests or readiness acceptance.</p> : null}
    <div className="flex flex-wrap gap-3">{(["comprehension", "critic"] as const).map(task => <Button key={task} type="button" variant="outline" disabled={busy || dirty || state.runs.filter(run => run.packet_id === state.current_packet_id && run.task === task).length >= 3} onClick={() => void review(task)}>Request fresh {task} review</Button>)}</div>
    <p className="text-xs text-muted-foreground">Up to three calls per review task and packet; planning is bounded to twelve calls per conversation. Save substantive revisions before further review. Usage is retained where available; missing charges are unknown.</p>
    {state.ready ? <p role="status" className="text-sm font-medium">Current packet accepted for protocol preparation. Scientific evidence is still separate.</p> : <form onSubmit={accept} className="space-y-3">
      <label className="block space-y-1 text-sm"><span className="font-medium">Readiness rationale</span><Input required disabled={busy} value={reason} onChange={event => { setReason(event.target.value); delete requests.current.accept; }} placeholder="Explain how you addressed the review findings." /></label>
      <Button type="submit" disabled={busy || dirty || !comprehension || !critic || state.missing.length > 0}>Accept current plan readiness</Button>
      {state.missing.length ? <p className="text-xs text-muted-foreground">Still required: {state.missing.join("; ")}</p> : null}
    </form>}
    {message ? <p role="status" className="rounded-md border p-3 text-sm">{message}</p> : null}
    <div className="space-y-3">{state.runs.length ? [...state.runs].reverse().map(run => <ModelAttempt key={run.id} run={run} packet={state.packets.find(row => row.id === run.packet_id)} />) : <p className="text-sm text-muted-foreground">No AI attempts recorded. Drafting a plan is not a review or an experiment.</p>}</div>
  </section>;
}

export function IdeaCampaign({ state, studyId, reload, dirty, onEditing, planningEndpoint = "idea" }: { planningEndpoint?: string; state: IdeaState; studyId: string; reload: () => Promise<void>; dirty: boolean; onEditing?: (editing: boolean) => void }) {
  const candidate = state.packets.find(row => row.id === state.current_packet_id)?.document.protocol;
  const [title, setTitle] = useState(""); const [stage, setStage] = useState(String(planningEndpoint === "claim-design" ? candidate?.stage ?? "pilot" : "pilot")); const [claimType, setClaimType] = useState("association");
  const [experimentType, setExperimentType] = useState(String(planningEndpoint === "claim-design" ? candidate?.experiment_type ?? "new-measurement" : "new-measurement")); const [units, setUnits] = useState(Number(state.packets.find(row => row.id === state.current_packet_id)?.document.protocol?.planned_units ?? 1));
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(""); const request = useRef("");
  const [queue, setQueue] = useState<Record<string, unknown>[] | null>(null);
  const [executionStatus, setExecutionStatus] = useState<{ networking?: NetworkingCapabilities; queue?: { workers_enabled?: boolean } } | null>(null);
  const [executionError, setExecutionError] = useState("");
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    researchRequest<{ networking?: NetworkingCapabilities; queue?: { workers_enabled?: boolean } }>("/capabilities", { signal: controller.signal }).then(status => {
      if (!controller.signal.aborted) { setExecutionStatus(status); setExecutionError(""); }
    }).catch(error => { if (!controller.signal.aborted) setExecutionError(errorText(error)); });
    return () => controller.abort();
  }, [availabilityRevision]);
  let runner: string | undefined;
  try { runner = typeof queue?.[0]?.raw_input === "string" ? JSON.parse(queue[0].raw_input).runner : undefined; } catch { /* An unreadable saved specification cannot authorize execution. */ }
  const automatic = queue?.every(request => request.execution_mode === "automatic");
  const executionBlocked = automatic && (executionStatus?.networking?.runners.find(item => item.id === runner)?.enabled !== true || executionStatus?.queue?.workers_enabled !== true);
  function changed() { request.current = ""; setQueue(null); onEditing?.(true); }
  async function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); request.current ||= crypto.randomUUID();
    try {
      const result = await researchRequest<{ link: { id: string; study_id: string }; queue_request: Record<string, unknown>; queue_requests?: Record<string, unknown>[] }>(`/studies/${studyId}/${planningEndpoint}`, { method: "POST", body: JSON.stringify({ action: "prepare-campaign", request_id: request.current, packet_id: state.current_packet_id, title, stage, claim_type: claimType, experiment_type: experimentType, planned_units: units }) });
      if (result.link.id !== request.current || result.link.study_id !== studyId) throw new Error("Campaign identity was not confirmed saved.");
      setQueue(preparedQueueRequests(result)); await reload(); onEditing?.(false); setMessage("Claim, source provenance, configurations and frozen protocol preserved. Queue the prepared experiment jobs when ready.");
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  async function enqueue() {
    if (!queue || executionBlocked) return; setBusy(true); setMessage("");
    try {
      for (const request of queue) {
        const result = await researchRequest<{ job: { id: string; campaign_id: string; study_id: string } }>(`/studies/${studyId}/queue`, { method: "POST", body: JSON.stringify(request) });
        if (result.job.id !== request.request_id || result.job.campaign_id !== request.campaign_id || result.job.study_id !== studyId) throw new Error("Queue persistence was not confirmed; inspect retained status before resuming.");
      }
      await reload(); setMessage(queue.every(request => request.execution_mode === "automatic") ? `${queue.length} automatic networking jobs queued. Enabled workers execute the frozen specifications and preserve measurements; scientific review remains separate.` : "Domain task queued. Supply an applicable implementation and recorded measurements for this manual task.");
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  async function resume(preparedId: string) {
    setBusy(true); setMessage("");
    try {
      const result = await researchRequest<{ queue_request: Record<string, unknown>; queue_requests?: Record<string, unknown>[] }>(`/studies/${studyId}/${planningEndpoint}`, { method: "POST", body: JSON.stringify({ action: "resume-campaign", prepared_id: preparedId }) });
      setQueue(preparedQueueRequests(result)); setMessage("Saved campaign reloaded. Queueing reuses original job identities and never restarts terminal runs.");
    } catch (failure) { setMessage(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <section className="space-y-4 rounded-lg border p-5" aria-labelledby="idea-campaign-title"><h2 id="idea-campaign-title" className="text-lg font-semibold">Preregister an experimental campaign</h2>
    <p className="text-sm text-muted-foreground">The accepted candidate protocol is frozen exactly as reviewed. An executable networking specification creates automatic jobs for its configurations and repetitions. Registered runners launch the actual tests and preserve measurements. Other domain work remains manual until it has an applicable implementation.</p>
    <form onSubmit={prepare} className="space-y-4">
      <label className="block space-y-1 text-sm"><span className="font-medium">Campaign title</span><Input required disabled={busy || !state.ready} value={title} onChange={event => { setTitle(event.target.value); changed(); }} /></label>
      <div className="grid gap-4 sm:grid-cols-2"><ResearchSelect label="Campaign stage" value={stage} onChange={value => { setStage(value); changed(); }} options={[{ value: "pilot", label: "Exploratory pilot" }, { value: "main", label: "Main campaign" }]} />{planningEndpoint === "idea" ? <ResearchSelect label="Hypothesis type" value={claimType} onChange={value => { setClaimType(value); changed(); }} options={["numerical", "algorithm", "association", "causal", "generalization", "operational", "theory"].map(value => ({ value, label: value }))} /> : null}<ResearchSelect label="Experiment method" value={experimentType} onChange={value => { setExperimentType(value); changed(); }} options={["new-measurement", "independent-check", "broader-validation"].map(value => ({ value, label: value }))} /><label className="block space-y-1 text-sm"><span className="font-medium">Planned experimental units</span><Input required type="number" min={1} max={10000} value={units} disabled={busy || !state.ready} onChange={event => { setUnits(Number(event.target.value)); changed(); }} /></label></div>
      <Button type="submit" disabled={busy || dirty || !state.ready}>{busy ? "Preserving campaign…" : "Freeze reviewed protocol and prepare campaign"}</Button>
    </form>
    {queue ? <Button type="button" variant="outline" disabled={busy || dirty || !!executionBlocked} onClick={() => void enqueue()}>{queue.every(request => request.execution_mode === "automatic") ? `Queue ${queue.length} networking experiment jobs` : "Queue domain experiment task"}</Button> : null}
    {executionBlocked ? <div role="status" className="space-y-2 rounded-md border p-3 text-sm"><p>{executionError || (!executionStatus ? "Checking whether this environment can execute the saved experiment…" : executionStatus.queue?.workers_enabled !== true ? "Experiment workers are not enabled in this environment. Your plan and prepared campaign are saved; execution is blocked until workers are enabled." : "This experiment runner is not enabled in the connected environment. Your plan and campaign are saved; execution is blocked until the runner is available.")}</p><Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => setAvailabilityRevision(value => value + 1)}>Check execution availability again</Button></div> : null}
    {state.campaigns.length ? <div className="space-y-2 text-sm"><p className="font-medium">Preserved campaign preparations</p>{state.campaigns.map(link => <div key={link.id} className="flex flex-wrap items-center gap-3"><span className="break-all text-xs">Campaign {link.campaign_id}</span><Button type="button" size="sm" variant="outline" disabled={busy || dirty} onClick={() => void resume(link.id)}>Resume queueing this campaign</Button></div>)}</div> : null}
    {message ? <p role="status" className="rounded-md border p-3 text-sm">{message}</p> : null}
    <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => { setTitle(""); setStage(String(planningEndpoint === "claim-design" ? candidate?.stage ?? "pilot" : "pilot")); setClaimType("association"); setExperimentType(String(planningEndpoint === "claim-design" ? candidate?.experiment_type ?? "new-measurement" : "new-measurement")); setUnits(Number(state.packets.find(row => row.id === state.current_packet_id)?.document.protocol?.planned_units ?? 1)); request.current = ""; setQueue(null); onEditing?.(false); setMessage("Unsaved campaign details discarded. Preserved campaigns remain available to resume."); }}>Discard unsaved campaign details</Button>
  </section>;
}

export function IdeaWorkspace({ studyId }: { studyId: string }) {
  const [state, setState] = useState<IdeaState | null>(null); const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null); const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [mode, setMode] = useState<"guided" | "advanced">("guided");
  const [draftSource, setDraftSource] = useState<"guided" | "advanced" | null>(null);
  const [campaignEditing, setCampaignEditing] = useState(false);
  const [versionConflict, setVersionConflict] = useState(false);
  const [guideRevision, setGuideRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([researchRequest(`/studies/${studyId}/idea`, { signal: controller.signal }), researchRequest(`/studies/${studyId}`, { signal: controller.signal })]).then(([idea, study]) => {
      if (!controller.signal.aborted) { setState(validateIdeaState(idea, studyId)); setSnapshot(validateSnapshot(study)); }
    }).catch(failure => { if (!controller.signal.aborted) setError(errorText(failure)); });
    return () => controller.abort();
  }, [studyId]);
  async function reload(expectedPacketId?: string, discardDraft = false) {
    const [idea, study] = await Promise.all([researchRequest(`/studies/${studyId}/idea`), researchRequest(`/studies/${studyId}`)]);
    const next = validateIdeaState(idea, studyId);
    if (!discardDraft && dirty && next.current_packet_id !== state?.current_packet_id && next.current_packet_id !== expectedPacketId) {
      setVersionConflict(true); setError("A newer plan version was saved elsewhere. Your open answer is preserved; save attempts against this older version will be rejected."); return;
    }
    if (next.current_packet_id !== state?.current_packet_id) { setDirty(false); setDraftSource(null); setCampaignEditing(false); }
    if (discardDraft) { setDirty(false); setDraftSource(null); setGuideRevision(value => value + 1); }
    setState(next); setSnapshot(validateSnapshot(study)); setError(""); setVersionConflict(false);
  }
  async function download() {
    if (!state) return;
    try {
      for (const packet of state.packets) {
        const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(packet.raw_document)))].map(value => value.toString(16).padStart(2, "0")).join("");
        if (digest !== packet.sha256) throw new Error("Packet download hash differs from the retained bytes.");
      }
      const url = URL.createObjectURL(new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `research-idea-${studyId}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setError(errorText(failure)); }
  }
  if (error && (!state || !snapshot)) return <section className="space-y-3 rounded-md border p-4"><p role="alert" className="text-sm text-destructive">{error}</p><Button type="button" variant="outline" onClick={() => void reload().catch(failure => setError(errorText(failure)))}>Retry loading retained idea</Button></section>;
  if (!state || !snapshot) return <p role="status">Loading your private research idea…</p>;
  const packet = state.packets.find(row => row.id === state.current_packet_id);
  return <div className="space-y-6"><section className="space-y-3 rounded-lg border p-5"><h2 className="text-xl font-semibold">{snapshot.study.title}</h2>
    {error ? <p role="alert" className="text-sm text-destructive">{error} Previously retrieved status is shown; your open answer is preserved. Refresh before relying on current readiness.</p> : null}
    {versionConflict ? <Button type="button" variant="outline" size="sm" onClick={() => void reload(undefined, true).catch(failure => setError(errorText(failure)))}>Discard this draft and load the newer plan</Button> : null}
    <p className="text-sm">Unpublished research idea · {packet ? `packet version ${packet.version}` : "first plan not yet saved"} · {state.ready ? "Plan readiness accepted" : "Draft / review pending"}</p>
    {!packet ? <p role="status" className="text-sm">Your study draft is preserved. Start answering below to save its first plan without creating another study.</p> : null}
    <div className="flex flex-wrap gap-2" aria-label="Planning interface"><Button type="button" size="sm" variant={mode === "guided" ? "default" : "outline"} aria-pressed={mode === "guided"} disabled={(dirty || campaignEditing) && mode !== "guided"} onClick={() => setMode("guided")}>Guided conversation</Button><Button type="button" size="sm" variant={mode === "advanced" ? "default" : "outline"} aria-pressed={mode === "advanced"} disabled={(dirty || campaignEditing) && mode !== "advanced"} onClick={() => setMode("advanced")}>Detailed editor and history</Button></div>
    <details open={mode === "advanced" || undefined} className="text-sm"><summary className="cursor-pointer"><span>History and results</span><span className="text-muted-foreground"> · {snapshot.records.runs.length} recorded runs</span></summary><div className="mt-3 space-y-3"><p className="text-muted-foreground">{snapshot.records.runs.length} scientific runs recorded. Saved plans are proposals. AI coaching and reviews are model outputs; measurements are recorded separately.</p><div className="flex flex-wrap gap-3"><Button type="button" variant="outline" size="sm" onClick={() => void download()}>Download planning history</Button><Button type="button" variant="outline" size="sm" onClick={() => void reload().catch(failure => setError(errorText(failure)))}>Refresh retained status</Button><Link className="text-sm underline" href={`${PATH}/workspace/${studyId}`}>Scientific evidence workspace</Link></div><details><summary className="cursor-pointer text-xs">Retained packet versions</summary><ul className="mt-2 space-y-1 text-xs">{state.packets.map(row => <li key={row.id} className="break-all">Version {row.version} · {row.reason} · SHA256 {row.sha256}</li>)}</ul></details></div></details>
  </section><div hidden={mode !== "guided"}><IdeaGuide key={guideRevision} state={state} studyId={studyId} dirty={dirty} advancedDirty={draftSource === "advanced" && dirty} active={mode === "guided"} campaignEditing={campaignEditing} onDirty={() => { setDirty(true); setDraftSource("guided"); }} onDiscard={() => { setDirty(false); setDraftSource(null); }} reload={reload}><IdeaCampaign key={`guided-campaign-${packet?.id}`} state={state} studyId={studyId} reload={reload} dirty={dirty} onEditing={setCampaignEditing} /></IdeaGuide></div>
    {mode === "advanced" ? <div className="space-y-6"><section className="space-y-4 rounded-lg border p-5"><h2 className="text-lg font-semibold">Self-contained research plan</h2><PacketEditor key={packet?.id ?? "initial"} packet={packet ?? null} studyId={studyId} onSaved={reload} onDirty={() => { setDirty(true); setDraftSource("advanced"); }} /></section><IdeaActions key={packet?.id ?? "initial"} state={state} studyId={studyId} reload={reload} dirty={dirty} /><IdeaCampaign key={`campaign-${packet?.id}`} state={state} studyId={studyId} reload={reload} dirty={dirty} onEditing={setCampaignEditing} /></div> : null}
    {state.campaigns.length || snapshot.records.runs.length ? <ClaimQueue snapshot={snapshot} onEvidenceChanged={reload} /> : null}
  </div>;
}
