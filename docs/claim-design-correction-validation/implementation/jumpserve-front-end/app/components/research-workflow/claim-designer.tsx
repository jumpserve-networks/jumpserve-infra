"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/app/components/ui/button";
import { Textarea } from "@/app/components/ui/textarea";
import { PacketEditor, IdeaActions, IdeaCampaign } from "@/app/components/research-ideas/idea-workspace";
import { researchRequest } from "@/lib/research-workflow-api";
import { ideaModelRequest } from "@/lib/research-idea-api";
import { CLAIM_DESIGN_VERSION, consumeClaimDesignIntent, validateClaimDesign, type ClaimDesignState } from "@/lib/research-claim-design";
import { experimentQueuePath } from "@/lib/research-experiment-queue";
import { RESEARCH_WORKFLOW_MODULE_PATH as PATH } from "@/lib/test-modules";

const errorText = (value: unknown) => value instanceof Error ? value.message : "Request was not confirmed. Your saved history remains available.";
async function verifiedState(value: unknown, studyId: string) {
  const state = validateClaimDesign(value, studyId);
  for (const row of [state.claim_design, ...state.packets]) {
    const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(row.raw_document)))].map(byte => byte.toString(16).padStart(2, "0")).join("");
    if (sha !== row.sha256) throw new Error("Retained planning bytes differ from their recorded hash.");
  }
  return state;
}

export function ClaimDesigner({ studyId }: { studyId: string }) {
  const [state, setState] = useState<ClaimDesignState | null>(null);
  const [message, setMessage] = useState(""); const [error, setError] = useState("");
  const [busy, setBusy] = useState(false); const [dirty, setDirty] = useState(false);
  const [answer, setAnswer] = useState("");
  const requests = useRef<Record<string, string>>({}); const session = useRef("");
  const draft = useRef<{ dirty: boolean; packetId: string | null }>({ dirty: false, packetId: null });
  const controller = useRef<AbortController | null>(null); const inFlight = useRef(false);
  const generateRef = useRef<() => void>(null);
  const endpoint = `/studies/${studyId}/claim-design`;
  const reload = useCallback(async (expectedPacketId?: string) => {
    const next = await verifiedState(await researchRequest(endpoint), studyId);
    if (draft.current.dirty && next.current_packet_id !== draft.current.packetId && next.current_packet_id !== expectedPacketId) throw new Error("A newer plan was saved elsewhere. Your editor text is preserved; copy it before reloading or resolving the version conflict.");
    setState(next); return next;
  }, [endpoint, studyId]);
  useEffect(() => { draft.current = { dirty, packetId: state?.current_packet_id ?? null }; }, [dirty, state?.current_packet_id]);
  useEffect(() => {
    const abort = new AbortController();
    researchRequest(endpoint, { signal: abort.signal }).then(async value => {
      const next = await verifiedState(value, studyId);
      if (!abort.signal.aborted) setState(next);
    }).catch(failure => { if (!abort.signal.aborted) setError(errorText(failure)); });
    return () => { abort.abort(); controller.current?.abort(); };
  }, [endpoint, studyId]);
  const packet = state?.packets.find(row => row.id === state.current_packet_id);
  async function generate(event?: FormEvent) {
    event?.preventDefault();
    if (!packet || dirty || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(""); setMessage("");
    requests.current.generate ||= crypto.randomUUID(); session.current ||= crypto.randomUUID();
    const abort = new AbortController(); controller.current = abort;
    try {
      const result = await ideaModelRequest({ design_version: CLAIM_DESIGN_VERSION, request_id: requests.current.generate, study_id: studyId, packet_id: packet.id,
        task: "planning", session_id: session.current, message: answer.trim() || "Design the most informative feasible experiment for this exact paper claim. Identify missing inputs and ask a tailored question. Keep proposed choices separate from known facts." }, abort.signal);
      if (abort.signal.aborted) return;
      await reload();
      if (result.run.status !== "running") { delete requests.current.generate; setAnswer(""); }
      setMessage(result.run.status === "complete" ? "Proposal recorded. Review its assumptions and adopt it as a new draft, or answer the questions to refine it." : `Attempt retained: ${result.run.status}. ${result.run.reason ?? "Inspect saved attempts before requesting another call."}`);
    } catch (failure) { if (!abort.signal.aborted) setError(errorText(failure)); }
    finally { inFlight.current = false; if (!abort.signal.aborted) setBusy(false); }
  }
  useEffect(() => { generateRef.current = () => { void generate(); }; });
  useEffect(() => {
    if (!state) return;
    const timer = setTimeout(() => {
      if (consumeClaimDesignIntent(studyId) && state.runs.length === 0) generateRef.current?.();
    }, 0);
    return () => clearTimeout(timer);
  }, [state, studyId]);
  async function adopt(runId: string, packetId: string) {
    if (inFlight.current || dirty) return;
    inFlight.current = true; setBusy(true); setError(""); requests.current[runId] ||= crypto.randomUUID();
    try {
      await researchRequest(endpoint, { method: "POST", body: JSON.stringify({ action: "adopt", request_id: requests.current[runId], run_id: runId, packet_id: packetId }) });
      await reload(); setDirty(false); setMessage("New draft version saved. Resolve remaining fields, then request fresh reviews before running.");
    } catch (failure) { setError(errorText(failure)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function download() {
    if (!state) return;
    try {
      await verifiedState(state, studyId);
      const url = URL.createObjectURL(new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = `claim-experiment-design-${studyId}.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setError(errorText(failure)); }
  }
  if (!state) return <section className="space-y-3 rounded-lg border p-5">{error ? <><p role="alert" className="text-destructive">{error}</p><Button onClick={() => void reload().catch(failure => setError(errorText(failure)))}>Retry loading saved design</Button></> : <p role="status">Loading the source-bound experiment design…</p>}</section>;
  const origin = state.claim_design.document;
  return <div className="space-y-6">
    <section className="space-y-3 rounded-lg border p-5">
      <h2 className="text-xl font-semibold">Design an experiment for this claim</h2>
      <blockquote className="border-l-2 pl-4">{origin.claim.description}</blockquote>
      <p className="text-sm text-muted-foreground">{origin.source.citation} · {origin.claim.location} · Source review: {origin.source.review_status}</p>
      <p className="break-all text-xs text-muted-foreground">Source SHA256: {origin.source.sha256 ?? "Unavailable; original bytes must be identified before automatic execution."}</p>
      <p className="text-sm">1. Develop a proposal with AI. 2. Save and review the plan. 3. Freeze the reviewed protocol and queue its experiment.</p>
      <p className="text-sm text-muted-foreground">The AI receives recorded claim and source metadata. A proposal is a draft; the original assessment stays unchanged. Unsupported equipment or implementations remain explicit operator work.</p>
      <p className="text-sm text-muted-foreground">This designer prepares descriptive pilots. JumpServe supplies their decision policy; overlap or a non-significant result cannot decide the paper claim. Inferential conclusions need a separately reviewed analysis design. To change a saved configuration, edit and save a new plan version before requesting fresh reviews.</p>
      <div className="flex flex-wrap gap-4 text-sm"><Link className="underline" href={`${PATH}/studies/${origin.study.id}?view=gaps`}>Original assessment</Link><Link className="underline" href={experimentQueuePath(studyId)}>Experiment Queue</Link><Link className="underline" href={`${PATH}/workspace/${studyId}`}>Evidence workspace</Link></div>
      <Button size="sm" variant="outline" onClick={() => void download()}>Download experiment design</Button>
    </section>
    {error ? <p role="alert" className="rounded-md border p-3 text-sm text-destructive">{error}</p> : null}
    {message ? <p role="status" className="rounded-md border p-3 text-sm">{message}</p> : null}
    <section className="space-y-4 rounded-lg border p-5" aria-labelledby="claim-design-conversation">
      <h2 id="claim-design-conversation" className="text-lg font-semibold">1. Develop the experiment</h2>
      <div className="space-y-4">{state.runs.filter(run => run.task === "planning").map(run => <article key={run.id} className="space-y-3 rounded-md border p-4 text-sm">
        <p className="font-medium">AI proposal · {run.status} · plan version {state.packets.find(row => row.id === run.packet_id)?.version}</p>
        {run.reason ? <p className="text-destructive">{run.reason}</p> : null}
        {run.output ? <><p className="whitespace-pre-wrap">{run.output.summary}</p>{run.output.questions.length ? <ul className="list-disc space-y-2 pl-5">{run.output.questions.map((question, i) => <li key={i}>{question}</li>)}</ul> : null}
          {run.output.decision_policy ? <p className="text-xs text-muted-foreground">Decision policy: {run.output.decision_policy.version}, supplied by JumpServe. {run.output.decision_policy.protocol_reused ? "The saved protocol was referenced; its configuration and resource settings were preserved." : "The AI authored the proposal text; JumpServe supplied the descriptive decision rule."}</p> : null}
          {run.output.proposal ? <><details><summary className="cursor-pointer">Review proposed plan and protocol</summary><pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all bg-muted p-3 text-xs">{JSON.stringify(run.output.proposal, null, 2)}</pre></details><Button size="sm" disabled={busy || dirty || run.packet_id !== state.current_packet_id} onClick={() => void adopt(run.id, run.packet_id)}>Adopt proposal as a new draft</Button></> : null}</> : null}
        <details><summary className="cursor-pointer text-xs">Prompt, evidence and usage</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ prompt_version_id: run.prompt_version_id, model_id: run.model_id, provenance: run.provenance, usage: run.usage }, null, 2)}</pre></details>
      </article>)}</div>
      <form onSubmit={generate} className="space-y-3">
        <label className="block space-y-1 text-sm"><span>Answer a question or describe your available data, equipment and constraints</span><Textarea aria-label="Experiment planning message" maxLength={4000} disabled={busy} value={answer} onChange={event => { setAnswer(event.target.value); delete requests.current.generate; }} /></label>
        <div className="flex flex-wrap gap-3"><Button type="submit" disabled={busy || dirty || !packet}>{busy ? "Designing…" : state.runs.some(run => run.task === "planning") ? "Refine experiment with AI" : "Design experiment with AI"}</Button><Button type="button" variant="outline" disabled={busy} onClick={() => { session.current = ""; delete requests.current.generate; setMessage("The next request starts a fresh conversation using the saved plan."); }}>New planning conversation</Button></div>
      </form>
      {dirty ? <p role="status" className="text-sm">Save your editor changes before requesting or adopting another proposal.</p> : null}
    </section>
    <section className="space-y-4 rounded-lg border p-5"><h2 className="text-lg font-semibold">2. Save the plan and resolve review findings</h2><p className="text-sm text-muted-foreground">Saved version {packet?.version ?? "unknown"}. Missing fields: {state.missing.length ? state.missing.join("; ") : "None reported by structural checks; fresh reviews still required."}</p>
      <fieldset disabled={busy}><PacketEditor key={packet?.id} packet={packet ?? null} studyId={studyId} planningEndpoint="claim-design" onDirty={() => setDirty(true)} onSaved={async expected => { await reload(expected); setDirty(false); }} /></fieldset>
    </section>
    <IdeaActions key={`reviews-${packet?.id}`} state={state} studyId={studyId} planningEndpoint="claim-design" dirty={dirty || busy} reload={async () => { await reload(); }} />
    <section className="space-y-3"><h2 className="text-lg font-semibold">3. Freeze the protocol and run</h2><IdeaCampaign key={`campaign-${packet?.id}`} state={state} studyId={studyId} planningEndpoint="claim-design" dirty={dirty || busy} reload={async () => { await reload(); }} /></section>
  </div>;
}
