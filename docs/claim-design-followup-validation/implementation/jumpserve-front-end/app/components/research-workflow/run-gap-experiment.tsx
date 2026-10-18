"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/app/components/ui/button";
import { requireAccessToken } from "@/lib/browser-auth";
import { researchRequest, ResearchRequestError } from "@/lib/research-workflow-api";
import { requireGapQueueApi } from "@/lib/research-queue-api";
import { experimentQueuePath, gapExperimentPath, validateGapPreview } from "@/lib/research-experiment-queue";
import { consumeGapRunIntent, runGapExperiments, saveGapRunIntent } from "@/lib/research-gap-run";
import { claimDesignPath, CLAIM_DESIGN_VERSION, saveClaimDesignIntent } from "@/lib/research-claim-design";
import { isResearchId } from "@/lib/research-experiment-queue";

export function RunGapExperiment({ studyId, gapId, launchId, onQueued }: { studyId: string; gapId: string; launchId?: string; onQueued?: (studyId: string, jobId: string) => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const [error, setError] = useState(""); const [savedStudy, setSavedStudy] = useState("");
  const requestId = useRef(""); const inFlight = useRef(false); const controller = useRef<AbortController | null>(null);
  const startRef = useRef<(id?: string) => Promise<void>>(null);
  useEffect(() => () => controller.current?.abort(), []);

  function signIn() {
    saveGapRunIntent(sessionStorage, { version: 1, studyId, gapId, requestId: requestId.current, createdAt: Date.now() });
    const next = `${gapExperimentPath(studyId, gapId)}&run=${requestId.current}`;
    router.push(`/login?${new URLSearchParams({ next })}`);
  }
  async function start(id?: string) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(""); setMessage("");
    if (id) requestId.current = id;
    if (!requestId.current) requestId.current = crypto.randomUUID();
    const abort = new AbortController(); controller.current = abort;
    try {
      try { await requireAccessToken(); }
      catch (failure) { if (abort.signal.aborted) return; if (failure instanceof Error && failure.message === "Sign in to run tests or chat with the AI.") { signIn(); return; } throw failure; }
      if (abort.signal.aborted) return;
      await requireGapQueueApi(researchRequest, abort.signal);
      const preview = validateGapPreview(await researchRequest(`/studies/${studyId}/gap-experiments?${new URLSearchParams({ gap_id: gapId })}`, { signal: abort.signal }), studyId, gapId);
      if (!preview.choices.length) {
        const capabilities = await researchRequest<{ preparation?: { claim_design_version?: string } }>("/capabilities", { signal: abort.signal });
        if (capabilities.preparation?.claim_design_version !== CLAIM_DESIGN_VERSION) throw new Error("This service needs the experiment designer update. Your original assessment is preserved.");
        setMessage("Creating or resuming a source-bound experiment design…");
        const design = await researchRequest<{ version: string; study_id: string }>(`/studies/${studyId}/gap-experiments`, { method: "POST", signal: abort.signal, body: JSON.stringify({ action: "design", request_id: requestId.current, gap_id: gapId, gap_sha256: preview.gap_sha256 }) });
        if (design.version !== CLAIM_DESIGN_VERSION || !isResearchId(design.study_id)) throw new Error("Experiment design persistence was not confirmed.");
        if (abort.signal.aborted) return;
        // A one-time, same-tab click intent permits the first AI proposal. A
        // pasted or prefetched designer URL alone cannot make a model call.
        saveClaimDesignIntent(design.study_id);
        router.push(claimDesignPath(design.study_id));
        return;
      }
      const result = await runGapExperiments(preview, requestId.current, (path, options) => researchRequest(path, { ...options, signal: abort.signal }), (text, study) => { if (!abort.signal.aborted) { setMessage(text); if (study) setSavedStudy(study); } });
      if (abort.signal.aborted) return;
      if (!result.complete) { setMessage("Some preparation was saved. The experiment is not fully queued yet; click Run experiment now to resume."); return; }
      setMessage("Jobs recorded. Ready automatic work can start when capacity is available; operator tasks and blocked work remain visible in Experiment Queue.");
      if (onQueued) onQueued(result.studyId, result.jobIds[0]);
      else router.push(experimentQueuePath(result.studyId, result.jobIds[0]));
    } catch (failure) {
      if (abort.signal.aborted) return;
      if (failure instanceof ResearchRequestError && failure.status === 401) { signIn(); return; }
      setError(`${failure instanceof Error ? failure.message : "Experiment could not be queued."} Any saved work is retained; retrying resumes the same job definitions.`);
    } finally { inFlight.current = false; if (!abort.signal.aborted) setBusy(false); }
  }
  useEffect(() => { startRef.current = start; });
  useEffect(() => {
    if (!launchId) return;
    // Only a recent same-tab click can resume a write after login. A pasted or
    // prefetched GET URL alone cannot launch an experiment.
    const timer = setTimeout(() => {
      try {
        const intent = consumeGapRunIntent(sessionStorage, launchId, studyId, gapId);
        if (intent) void startRef.current?.(intent.requestId);
      } catch { setError("The saved sign-in action could not be resumed. Click Run experiment now to continue."); }
    }, 0);
    return () => clearTimeout(timer);
  }, [launchId, studyId, gapId]);
  return <div className="space-y-2">
    <Button size="sm" disabled={busy} onClick={() => void start()}>{busy ? "Preparing and queueing…" : "Run experiment now"}</Button>
    {message ? <p role="status" className="text-xs text-muted-foreground">{message}</p> : null}
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    {savedStudy ? <Link className="block text-xs underline" href={experimentQueuePath(savedStudy)}>View saved work in Experiment Queue</Link> : null}
  </div>;
}
