import { SessionView } from "@/components/SessionView";

type SessionPageProps = {
  params: Promise<{ sessionId: string }>;
};

export default async function SessionPage({ params }: SessionPageProps) {
  const { sessionId } = await params;
  return <SessionView sessionId={sessionId} />;
}
