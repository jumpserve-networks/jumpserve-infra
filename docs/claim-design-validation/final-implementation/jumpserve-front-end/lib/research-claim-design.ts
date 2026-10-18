import { isResearchId } from "./research-experiment-queue";
import { normalizedJson, validateIdeaState, type IdeaState } from "./research-ideas";
import { RESEARCH_WORKFLOW_MODULE_PATH } from "./test-modules";

export const CLAIM_DESIGN_VERSION = "claim-experiment-design-v1";
export function saveClaimDesignIntent(studyId: string) {
  try { sessionStorage.setItem(`claim-design-start-v1:${studyId}`, String(Date.now())); }
  catch { /* The saved workspace remains usable through its explicit AI button. */ }
}
export function consumeClaimDesignIntent(studyId: string, storage?: Pick<Storage, "getItem" | "removeItem">, now = Date.now()) {
  const key = `claim-design-start-v1:${studyId}`;
  try {
    storage ??= sessionStorage;
    const raw = storage.getItem(key); storage.removeItem(key); const time = Number(raw);
    return Boolean(raw && Number.isFinite(time) && time <= now && now - time < 15 * 60 * 1000);
  } catch { return false; }
}
export function claimDesignPath(studyId: string) {
  if (!isResearchId(studyId)) throw new Error("Invalid claim design workspace identity.");
  return `${RESEARCH_WORKFLOW_MODULE_PATH}/experiment-design/${studyId}`;
}
export type ClaimDesignState = IdeaState & { design_version: string; claim_design: { study_id: string; sha256: string; raw_document: string; document: { study: { id: string; title: string }; claim: { id: string; description: string; location: string }; source: { citation: string; sha256: string | null; review_status: string }; gap: { id: string; reason: string } } } };
export function validateClaimDesign(value: unknown, studyId: string): ClaimDesignState {
  const state = validateIdeaState(value, studyId) as ClaimDesignState;
  if (state.design_version !== CLAIM_DESIGN_VERSION || state.claim_design?.study_id !== studyId || !/^[a-f0-9]{64}$/.test(state.claim_design.sha256) || !state.claim_design.document?.claim?.description) throw new Error("Source-bound claim design context was not confirmed.");
  if (normalizedJson(JSON.parse(state.claim_design.raw_document)) !== normalizedJson(state.claim_design.document)) throw new Error("Parsed claim context differs from the retained original bytes.");
  if (state.packets.some(packet => packet.document.hypothesis !== state.claim_design.document.claim.description)) throw new Error("Saved hypothesis differs from the retained paper claim.");
  return state;
}
