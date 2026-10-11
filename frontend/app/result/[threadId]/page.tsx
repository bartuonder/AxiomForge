import { PaperView } from "./paper-view";

type ResultPageProps = {
  params: Promise<{ threadId: string }>;
};

export default async function ResultPage({ params }: ResultPageProps) {
  const { threadId } = await params;
  return <PaperView threadId={threadId} />;
}
