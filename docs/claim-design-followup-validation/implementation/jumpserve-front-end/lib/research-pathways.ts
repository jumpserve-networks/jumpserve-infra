import { RESEARCH_IDEAS_MODULE_PATH, RESEARCH_WORKFLOW_MODULE_PATH } from "./test-modules";
import type { ResearchStudy } from "./research-workflow";

export type ResearchStudyKind = "paper" | "idea";

// Older paper assessments predate study_kind. Their existing identities stay intact.
export function researchStudyKind(study: Pick<ResearchStudy, "study_kind">): ResearchStudyKind {
  return study.study_kind === "idea" ? "idea" : "paper";
}

export function researchModulePath(kind: ResearchStudyKind) {
  return kind === "idea" ? RESEARCH_IDEAS_MODULE_PATH : RESEARCH_WORKFLOW_MODULE_PATH;
}

export function studiesForPathway(studies: ResearchStudy[], kind: ResearchStudyKind) {
  return studies.filter(study => researchStudyKind(study) === kind);
}

export function researchWorkspacePath(study: Pick<ResearchStudy, "id" | "study_kind" | "claim_design">) {
  const kind = researchStudyKind(study);
  if (kind === "paper" && study.claim_design === true) return `${RESEARCH_WORKFLOW_MODULE_PATH}/experiment-design/${study.id}`;
  return `${researchModulePath(kind)}/${kind === "idea" ? "ideas" : "workspace"}/${study.id}`;
}

export function researchSearchSuffix(query: Record<string, string | string[] | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) search.append(key, item);
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}
