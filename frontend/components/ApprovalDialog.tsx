"use client";

type ApprovalDialogProps = {
  hypotheses: string[];
  busy: boolean;
  onDecide: (decision: "Y" | "N") => void;
};

export function ApprovalDialog({ hypotheses, busy, onDecide }: ApprovalDialogProps) {
  return (
    <section className="mx-auto w-full max-w-3xl rounded-3xl border border-[#d7d0c4] bg-white p-6 shadow-[0_20px_60px_rgba(28,25,21,0.08)]">
      <p className="text-xs font-semibold tracking-[0.16em] text-[#1f6b4a] uppercase">
        Plan paused
      </p>
      <h2 className="mt-2 text-2xl text-[#1c1915]">Approve these hypotheses?</h2>
      <ol className="mt-5 space-y-3">
        {hypotheses.map((item, index) => (
          <li key={item} className="rounded-2xl bg-[#f6f1e8] px-4 py-3 text-sm leading-6 text-[#1c1915]">
            <span className="mr-2 font-semibold text-[#1f6b4a]">{index + 1}.</span>
            {item}
          </li>
        ))}
      </ol>
      <div className="mt-6 flex gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide("Y")}
          className="h-11 rounded-full bg-[#1f6b4a] px-5 text-sm font-semibold text-white disabled:bg-[#8aa898]"
        >
          Onayla (Y)
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide("N")}
          className="h-11 rounded-full border border-[#d7d0c4] px-5 text-sm font-semibold text-[#1c1915] disabled:text-[#8a8175]"
        >
          Reddet (N)
        </button>
      </div>
    </section>
  );
}
