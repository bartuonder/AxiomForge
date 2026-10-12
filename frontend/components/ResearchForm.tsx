"use client";

type ResearchFormProps = {
  query: string;
  busy: boolean;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
};

export function ResearchForm({ query, busy, onQueryChange, onSubmit }: ResearchFormProps) {
  return (
    <form
      className="flex w-full flex-col gap-3 sm:flex-row"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="sr-only" htmlFor="research-query">
        Research topic
      </label>
      <input
        id="research-query"
        value={query}
        disabled={busy}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="What should the agents study?"
        className="h-12 flex-1 rounded-full border border-[#d7d0c4] bg-white px-5 text-[15px] text-[#1c1915] outline-none placeholder:text-[#a3988c] focus:border-[#1f6b4a] disabled:bg-[#f7f4ee]"
      />
      <button
        type="submit"
        disabled={busy || query.trim().length === 0}
        className="h-12 cursor-pointer rounded-full bg-[#1f6b4a] px-6 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#d5d0c6] disabled:text-[#6f675e]"
      >
        {busy ? "Running" : "Start Research"}
      </button>
    </form>
  );
}
