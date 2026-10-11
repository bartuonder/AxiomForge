"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { fetchReport } from "@/lib/api";

type PaperViewProps = {
  threadId: string;
};

export function PaperView({ threadId }: PaperViewProps) {
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!threadId) {
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const next = await fetchReport(threadId);
        if (!cancelled) {
          setMarkdown(next);
          setError("");
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Report is not ready");
        }
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [threadId]);

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-6 py-16">
      <Link href="/" className="text-sm font-semibold text-[#1f6b4a]">
        Back to console
      </Link>
      <p className="mt-8 text-xs font-semibold tracking-[0.18em] text-[#8a8175] uppercase">Workshop paper</p>
      <h1 className="mt-2 text-4xl text-[#1c1915]">Research report</h1>
      {error && !markdown ? <p className="mt-8 text-sm text-[#9b3d2b]">{error}</p> : null}
      {markdown ? (
        <article className="paper mt-10 space-y-4 text-[17px] leading-8 text-[#1c1915]">
          <ReactMarkdown>{markdown}</ReactMarkdown>
        </article>
      ) : null}
    </main>
  );
}
