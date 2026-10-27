"use client";

import type { ReactNode } from "react";

export type TabItem = { id: string; label: string; content: ReactNode };

type TabsProps = {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
};

export function Tabs({ items, active, onChange }: TabsProps) {
  const current = items.find((item) => item.id === active) ?? items[0];
  return (
    <div>
      <div role="tablist" className="flex gap-1 border-b border-[#d7d0c4]">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`tab-${item.id}`}
            aria-selected={item.id === current.id}
            aria-controls={`panel-${item.id}`}
            onClick={() => onChange(item.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${
              item.id === current.id ? "border-[#1f6b4a] text-[#1f6b4a]" : "border-transparent text-[#5c564e] hover:text-[#1c1915]"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${current.id}`} aria-labelledby={`tab-${current.id}`} className="pt-8">
        {current.content}
      </div>
    </div>
  );
}
