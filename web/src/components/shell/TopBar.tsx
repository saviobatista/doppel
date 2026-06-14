"use client";

import { Sparkles, Bell } from "lucide-react";

export function TopBar({ actions }: { actions?: React.ReactNode }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-end gap-3 px-6">
      {actions}

      <button className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm font-medium text-zinc-200 transition-colors hover:border-white/20 hover:bg-white/10">
        <Sparkles className="h-4 w-4 text-accent" />
        Perguntar à IA
      </button>

      <button className="relative flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-zinc-300 transition-colors hover:bg-white/10">
        <Bell className="h-[18px] w-[18px]" />
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
          1
        </span>
      </button>

      <button className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-blue-700 text-sm font-semibold text-white">
        B
      </button>
    </header>
  );
}
