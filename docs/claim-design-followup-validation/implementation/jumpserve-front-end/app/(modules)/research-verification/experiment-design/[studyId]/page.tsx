import { notFound } from "next/navigation";
import { ResearchHeader } from "@/app/components/research-workflow/header";
import { ClaimDesigner } from "@/app/components/research-workflow/claim-designer";
import { requireGoogleUser } from "@/lib/auth";
import { claimDesignPath } from "@/lib/research-claim-design";
import { isResearchId } from "@/lib/research-experiment-queue";

export const dynamic = "force-dynamic";
export default async function ExperimentDesign({ params }: { params: Promise<{ studyId: string }> }) {
  const { studyId } = await params;
  if (!isResearchId(studyId)) notFound();
  await requireGoogleUser(claimDesignPath(studyId));
  return <main className="mx-auto max-w-6xl space-y-6 px-4 py-6"><ResearchHeader title="Experiment designer" /><ClaimDesigner studyId={studyId} /></main>;
}
