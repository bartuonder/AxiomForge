import { CampaignView } from "./campaign-view";

type CampaignPageProps = {
  params: Promise<{ campaignId: string }>;
};

export default async function CampaignPage({ params }: CampaignPageProps) {
  const { campaignId } = await params;
  return <CampaignView campaignId={campaignId} />;
}
