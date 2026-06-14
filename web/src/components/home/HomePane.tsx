"use client";

import Link from "next/link";
import { Plus, ChevronDown, Check, Circle } from "lucide-react";

const ONBOARDING = [
  { label: "Crie Seu Avatar", done: false },
  { label: "Clone sua voz", done: true },
  { label: "Criar um Vídeo", done: true },
];

const RECENTS = [{ title: "Milionários com IA", when: "21 horas atrás" }];

export function HomePane() {
  const doneCount = ONBOARDING.filter((o) => o.done).length;

  return (
    <div className="space-y-4">
      <Link
        href="/avatar/studio"
        className="flex items-center gap-2 rounded-xl bg-accent/15 px-3 py-2.5 text-sm font-semibold text-accent ring-1 ring-accent/30 transition-colors hover:bg-accent/20"
      >
        <Plus className="h-4 w-4" />
        Criar Novo
      </Link>

      {/* Onboarding checklist */}
      <div className="rounded-xl border border-white/5 bg-white/[0.02] p-1">
        <button className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-sm text-zinc-200 hover:bg-white/5">
          <span className="flex items-center gap-2">
            <Circle className="h-4 w-4 text-accent" />
            Começar
          </span>
          <span className="flex items-center gap-2 text-xs text-zinc-500">
            {doneCount}/{ONBOARDING.length}
            <ChevronDown className="h-4 w-4" />
          </span>
        </button>
        <div className="space-y-0.5 px-1 pb-1">
          {ONBOARDING.map((o) => (
            <div
              key={o.label}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm"
            >
              <span
                className={
                  o.done
                    ? "flex h-4 w-4 items-center justify-center rounded-full bg-accent text-obsidian"
                    : "flex h-4 w-4 items-center justify-center rounded-full border border-zinc-600"
                }
              >
                {o.done && <Check className="h-3 w-3" strokeWidth={3} />}
              </span>
              <span className={o.done ? "text-zinc-500 line-through" : "text-zinc-200"}>
                {o.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Recents */}
      <div>
        <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-600">
          Ontem
        </p>
        <div className="space-y-0.5">
          {RECENTS.map((r) => (
            <button
              key={r.title}
              className="flex w-full flex-col items-start rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-white/5"
            >
              <span className="text-sm text-zinc-200">{r.title}</span>
              <span className="text-xs text-zinc-600">{r.when}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
