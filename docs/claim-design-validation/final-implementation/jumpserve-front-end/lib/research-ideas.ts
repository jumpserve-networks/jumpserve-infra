export const IDEA_VERSION = "research-ideas-v1";
export const IDEA_FIELDS = ["problem", "question", "hypothesis", "conditions", "related_work", "alternatives", "design", "metrics", "controls", "falsification", "inputs", "limitations"] as const;
export type IdeaDocument = Record<typeof IDEA_FIELDS[number], string> & { protocol: Record<string, unknown> | null };
export type IdeaPacket = { id: string; study_id: string; version: number; supersedes_id: string | null; document: IdeaDocument; raw_document: string; sha256: string; reason: string; created_at: string };
export type IdeaTask = "planning" | "comprehension" | "critic";
export type IdeaOutput = { summary: string; questions: string[]; proposal?: IdeaDocument; findings: { severity: "blocking" | "warning"; field: string; message: string }[]; verdict: "ready" | "needs-clarification" };
export type IdeaRun = { id: string; study_id: string; packet_id: string; task: IdeaTask; session_id: string | null; status: "running" | "complete" | "failed" | "invalid-output"; reason: string | null; output: IdeaOutput | null; model_id: string; prompt_version_id: string; provenance: Record<string, unknown>; usage: Record<string, unknown> | null; created_at: string };
export type IdeaState = { version: string; packets: IdeaPacket[]; runs: IdeaRun[]; decisions: { id: string; study_id: string; packet_id: string; comprehension_run_id: string; critic_run_id: string; decision: "ready" }[]; campaigns: { id: string; study_id: string; packet_id: string; campaign_id: string; protocol_id: string }[]; current_packet_id: string | null; ready: boolean; missing: string[]; limitations: string };
export function emptyIdea(): IdeaDocument { return { ...Object.fromEntries(IDEA_FIELDS.map(field => [field, ""])) as Record<typeof IDEA_FIELDS[number], string>, protocol: null }; }
export function normalizedJson(value: unknown): string {
  const normalize = (item: unknown): unknown => Array.isArray(item) ? item.map(normalize) : item && typeof item === "object" ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, normalize(child)])) : item;
  return JSON.stringify(normalize(value));
}

export function validateIdeaState(value: unknown, studyId: string): IdeaState {
  const state = value as IdeaState;
  if (!state || state.version !== IDEA_VERSION || typeof state.ready !== "boolean" || !Array.isArray(state.missing)) throw new Error("Idea response is incomplete or unsupported.");
  for (const key of ["packets", "runs", "decisions", "campaigns"] as const) {
    if (!Array.isArray(state[key]) || new Set(state[key].map(row => row.id)).size !== state[key].length || state[key].some(row => row.study_id !== studyId)) throw new Error("Idea history has incomplete or conflicting study identities.");
  }
  const packets = new Map(state.packets.map(packet => [packet.id, packet]));
  for (const packet of state.packets) {
    if (!Number.isSafeInteger(packet.version) || packet.version < 1 || !/^[a-f0-9]{64}$/.test(packet.sha256) || normalizedJson(JSON.parse(packet.raw_document)) !== normalizedJson(packet.document)) throw new Error("Idea packet has invalid version, hash or parsed bytes.");
  }
  if (state.current_packet_id !== null && !packets.has(state.current_packet_id)) throw new Error("Current idea packet is unavailable.");
  if (state.ready && state.missing.length) throw new Error("An incomplete plan cannot be marked ready.");
  for (const run of state.runs) {
    if (!packets.has(run.packet_id) || !["planning", "comprehension", "critic"].includes(run.task) || !["running", "complete", "failed", "invalid-output"].includes(run.status)) throw new Error("Idea attempt has an invalid state or packet reference.");
    if (run.task !== "planning" && (run.session_id !== null || run.provenance.context_policy !== "fresh-packet-only" || run.provenance.history_messages !== 0)) throw new Error("Review context is not confirmed fresh.");
  }
  if (state.ready && !state.decisions.some(row => row.packet_id === state.current_packet_id && row.decision === "ready" && row.comprehension_run_id === ideaReview(state, "comprehension")?.id && row.critic_run_id === ideaReview(state, "critic")?.id && row.comprehension_run_id && row.critic_run_id)) throw new Error("Readiness is not recorded for the current packet and its latest reviews.");
  return state;
}
export function ideaReview(state: IdeaState, task: "comprehension" | "critic") {
  const latest = [...state.runs].reverse().find(run => run.packet_id === state.current_packet_id && run.task === task);
  return latest?.status === "complete" && latest.output?.verdict === "ready" && latest.output.questions.length === 0 && !latest.output.findings.some(finding => finding.severity === "blocking") ? latest : undefined;
}
