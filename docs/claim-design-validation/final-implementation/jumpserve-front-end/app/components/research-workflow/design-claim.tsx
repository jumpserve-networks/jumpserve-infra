"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/app/components/ui/button";
import { researchRequest } from "@/lib/research-workflow-api";
import { claimDesignPath, CLAIM_DESIGN_VERSION, saveClaimDesignIntent } from "@/lib/research-claim-design";
import { isResearchId } from "@/lib/research-experiment-queue";

type Selection = { version: string; study_id: string; claim_id: string; claim_sha256: string; claim: { description: string; location: string }; source: { citation: string } };
export function DesignClaim({ studyId, claimId }: { studyId: string; claimId: string }) {
  const router = useRouter(); const [selection, setSelection] = useState<Selection | null>(null);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const request = useRef("");
  const endpoint = `/studies/${studyId}/gap-experiments`;
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const capabilities = await researchRequest<{ preparation?: { claim_design_version?: string } }>("/capabilities", { signal: controller.signal });
      if (capabilities.preparation?.claim_design_version !== CLAIM_DESIGN_VERSION) throw new Error("The connected research service needs the experiment designer update. Your original claim and assessment remain preserved.");
      return researchRequest<Selection>(`${endpoint}?${new URLSearchParams({ claim_id: claimId })}`, { signal: controller.signal });
    }
    load().then(value => {
      if (controller.signal.aborted) return;
      if (value.version !== CLAIM_DESIGN_VERSION || value.study_id !== studyId || value.claim_id !== claimId || !/^[a-f0-9]{64}$/.test(value.claim_sha256) || !value.claim?.description) throw new Error("Exact claim selection was not confirmed.");
      setSelection(value);
    }).catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Claim could not be loaded."); });
    return () => controller.abort();
  }, [endpoint, studyId, claimId]);
  async function start() {
    if (!selection || busy) return; setBusy(true); setError(""); request.current ||= crypto.randomUUID();
    try {
      const result = await researchRequest<{ version: string; study_id: string }>(endpoint, { method: "POST", body: JSON.stringify({ action: "design", request_id: request.current, claim_id: claimId, claim_sha256: selection.claim_sha256 }) });
      if (result.version !== CLAIM_DESIGN_VERSION || !isResearchId(result.study_id)) throw new Error("Saved design identity was not confirmed.");
      saveClaimDesignIntent(result.study_id);
      router.push(claimDesignPath(result.study_id));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Design preparation was not confirmed."); setBusy(false); }
  }
  return <section className="space-y-4 rounded-lg border p-5">{selection ? <><blockquote className="border-l-2 pl-4">{selection.claim.description}</blockquote><p className="text-sm text-muted-foreground">{selection.source.citation} · {selection.claim.location}</p><p className="text-sm">Create or resume a private, source-bound experiment design. AI will propose a method and ask about missing inputs. Review and freeze the plan before running its experiment.</p><Button disabled={busy} onClick={() => void start()}>{busy ? "Preparing design…" : "Design experiment with AI"}</Button></> : !error ? <p role="status">Loading the selected claim…</p> : null}{error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}</section>;
}
