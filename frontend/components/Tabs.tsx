"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { nextTabIndex } from "@/lib/tabs";

export type TabItem = { id: string; label: string; content: ReactNode };

type TabsProps = {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
};

export function Tabs({ items, active, onChange }: TabsProps) {
  const current = items.find((item) => item.id === active) ?? items[0];
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const target = nextTabIndex(event.key, index, items.length);
    if (target === null) {
      return;
    }
    event.preventDefault();
    onChange(items[target].id);
    buttons.current[target]?.focus();
  };

  return (
    <div>
      <div role="tablist" className="flex gap-1 border-b border-line">
        {items.map((item, index) => (
          <button
            key={item.id}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            type="button"
            role="tab"
            id={`tab-${item.id}`}
            aria-selected={item.id === current.id}
            aria-controls={`panel-${item.id}`}
            tabIndex={item.id === current.id ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${
              item.id === current.id ? "border-accent text-accent" : "border-transparent text-muted hover:text-ink"
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
