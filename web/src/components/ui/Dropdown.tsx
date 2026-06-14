"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Check, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export interface DropdownOption {
  value: string;
  label: string;
}

interface DropdownProps {
  value: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
  icon?: LucideIcon;
  placeholder?: string;
  /** Which side the menu opens toward. */
  side?: "top" | "bottom";
  align?: "start" | "end";
  emptyLabel?: string;
  className?: string;
  /** Optional decoration rendered behind the button content (e.g. an audio meter). */
  meter?: ReactNode;
}

export function Dropdown({
  value,
  options,
  onChange,
  icon: Icon,
  placeholder = "Selecionar",
  side = "bottom",
  align = "start",
  emptyLabel = "Nenhum dispositivo",
  className,
  meter,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = options.find((o) => o.value === value);

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "relative flex items-center gap-2 overflow-hidden rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-zinc-200 transition-colors hover:border-white/20 hover:bg-white/10",
          open && "border-accent/40",
        )}
      >
        {meter}
        {Icon && <Icon className="relative h-4 w-4 shrink-0 text-zinc-400" />}
        <span className="relative max-w-[150px] truncate">{current?.label ?? placeholder}</span>
        <ChevronDown
          className={cn(
            "relative h-3.5 w-3.5 shrink-0 text-zinc-500 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div
          className={cn(
            "absolute z-30 min-w-[200px] rounded-xl border border-white/10 bg-panel-2 p-1 shadow-2xl shadow-black/50",
            side === "top" ? "bottom-full mb-2" : "top-full mt-2",
            align === "end" ? "right-0" : "left-0",
          )}
        >
          {options.length === 0 && (
            <p className="px-2.5 py-2 text-sm text-zinc-500">{emptyLabel}</p>
          )}
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                o.value === value
                  ? "bg-accent/15 text-accent"
                  : "text-zinc-200 hover:bg-white/5",
              )}
            >
              <span className="truncate">{o.label}</span>
              {o.value === value && <Check className="h-4 w-4 shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
