import { requireAccessToken } from "@/lib/browser-auth";
import { researchApiBase } from "@/lib/research-workflow";
import { IDEA_VERSION, type IdeaRun } from "@/lib/research-ideas";
export class IdeaRequestError extends Error {
  readonly uncertain: boolean;
  constructor(message: string, uncertain: boolean) { super(message); this.uncertain = uncertain; this.name = "IdeaRequestError"; }
}

export async function ideaModelRequest(body: Record<string, unknown>, signal?: AbortSignal): Promise<{ run: IdeaRun }> {
  let origin: string | undefined; let token: string;
  try { origin = researchApiBase(process.env.NEXT_PUBLIC_AGENT_URL); }
  catch (error) { throw new IdeaRequestError(error instanceof Error ? error.message : "AI configuration or sign-in could not be verified.", false); }
  if (!origin) throw new IdeaRequestError("Idea AI is not configured. Your saved packet remains available.", false);
  try { token = await requireAccessToken(); }
  catch (error) { throw new IdeaRequestError(error instanceof Error ? error.message : "Sign in before requesting AI help.", false); }
  let invocationStarted = false;
  const controller = new AbortController();
  const relay = () => controller.abort(signal?.reason);
  if (signal?.aborted) relay(); else signal?.addEventListener("abort", relay, { once: true });
  const timeout = setTimeout(() => controller.abort(new Error("AI request timed out. Refresh retained attempts before requesting another call.")), 90000);
  async function request(payload: Record<string, unknown>) {
    const response = await fetch(origin!, { method: "POST", signal: controller.signal, cache: "no-store", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload) });
    let result;
    try { result = await response.json(); } catch { throw new Error(`Idea AI returned an unreadable response (HTTP ${response.status}).`); }
    if (!response.ok) throw new IdeaRequestError(result.error ?? `Idea AI request failed (HTTP ${response.status}).`, invocationStarted && response.status >= 500);
    return result;
  }
  try {
    const capabilities = await request({ action: "capabilities" });
    if (capabilities.research_ideas?.version !== IDEA_VERSION) throw new IdeaRequestError("This AI service does not yet support the idea flow. No model call was requested.", false);
    if (body.design_version && capabilities.research_ideas?.claim_design_version !== body.design_version) throw new IdeaRequestError("The AI experiment designer is not available on this service yet. Your saved draft remains available. No model call was requested.", false);
    if (body.interview_version && capabilities.research_ideas?.interview_version !== body.interview_version) throw new IdeaRequestError("The conversational guide is not available on this AI service yet. Use the checklist meanwhile. No model call was requested.", false);
    invocationStarted = true;
    const result = await request({ ...body, action: "idea" });
    if (!result.run || result.run.id !== body.request_id || result.run.study_id !== body.study_id || result.run.packet_id !== body.packet_id || result.run.task !== body.task) throw new Error("AI attempt identity was not confirmed. Refresh retained history before continuing.");
    return result;
  } catch (error) { throw error instanceof IdeaRequestError ? error : new IdeaRequestError(error instanceof Error ? error.message : "AI response is unconfirmed; refresh retained status.", invocationStarted); }
  finally { clearTimeout(timeout); signal?.removeEventListener("abort", relay); }
}
