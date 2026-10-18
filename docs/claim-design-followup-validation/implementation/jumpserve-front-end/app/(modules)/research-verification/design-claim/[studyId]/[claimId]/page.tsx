import { notFound } from "next/navigation";
import { ResearchHeader } from "@/app/components/research-workflow/header";
import { DesignClaim } from "@/app/components/research-workflow/design-claim";
import { requireGoogleUser } from "@/lib/auth";
import { isResearchId } from "@/lib/research-experiment-queue";
import { RESEARCH_WORKFLOW_MODULE_PATH as PATH } from "@/lib/test-modules";
export const dynamic = "force-dynamic";
export default async function DesignClaimPage({ params }: { params: Promise<{ studyId: string; claimId: string }> }) {
  const { studyId, claimId } = await params;
  if (!isResearchId(studyId) || !isResearchId(claimId)) notFound();
  await requireGoogleUser(`${PATH}/design-claim/${studyId}/${claimId}`);
  return <main className="mx-auto max-w-6xl space-y-6 px-4 py-6"><ResearchHeader title="Design a claim experiment" /><DesignClaim studyId={studyId} claimId={claimId} /></main>;
}
