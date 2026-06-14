"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Clapperboard, Film, Loader2, Plus, Sparkles } from "lucide-react";
import { listPlans } from "@/lib/api";
import type { PlanStatus, PlanSummary } from "@/lib/videoPlan";
import { cn } from "@/lib/cn";

const STATUS_LABEL: Record<PlanStatus, string> = {
  researching: "Pesquisando",
  scripting: "Roteirizando",
  directing: "Dirigindo",
  ready: "Pronto",
  generating: "Gerando vídeo",
  generated: "Vídeo pronto",
  failed: "Falhou",
};

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "agora";
  if (s < 3600) return `${Math.floor(s / 60)} min atrás`;
  if (s < 86400) return `${Math.floor(s / 3600)} h atrás`;
  return `${Math.floor(s / 86400)} d atrás`;
}

export function ProjectsGrid() {
  const [plans, setPlans] = useState<PlanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPlans()
      .then(setPlans)
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Projetos</h1>
          <p className="mt-2 text-zinc-400">Suas sessões do Agente de Vídeo — clique para reabrir.</p>
        </div>
        <Link
          href="/agente"
          className="flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
        >
          <Plus className="h-4 w-4" />
          Novo
        </Link>
      </div>

      {error && <p className="mt-8 text-sm text-red-300">{error}</p>}

      {plans === null && !error && (
        <div className="mt-16 flex justify-center text-zinc-500">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      )}

      {plans?.length === 0 && (
        <div className="mt-16 flex flex-col items-center gap-3 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/15 text-accent ring-1 ring-accent/30">
            <Sparkles className="h-6 w-6" />
          </span>
          <p className="text-zinc-400">Nenhuma sessão ainda.</p>
          <Link
            href="/agente"
            className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-obsidian hover:bg-accent-strong"
          >
            Criar a primeira
          </Link>
        </div>
      )}

      {plans && plans.length > 0 && (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {plans.map((p) => (
            <Link
              key={p.plan_id}
              href={`/agente/${p.plan_id}`}
              className="group overflow-hidden rounded-2xl border border-white/10 bg-panel transition-colors hover:border-accent/40"
            >
              <div className="relative flex aspect-video items-center justify-center bg-gradient-to-br from-white/10 to-white/[0.02]">
                {p.cover_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.cover_url} alt={p.title} className="h-full w-full object-cover" />
                ) : (
                  <Clapperboard className="h-8 w-8 text-zinc-600" />
                )}
                <span
                  className={cn(
                    "absolute left-2 top-2 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1",
                    p.status === "failed"
                      ? "bg-red-500/15 text-red-300 ring-red-500/30"
                      : p.status === "generated" || p.status === "ready"
                        ? "bg-neon-green/15 text-neon-green ring-neon-green/30"
                        : "bg-accent/15 text-accent ring-accent/30",
                  )}
                >
                  {STATUS_LABEL[p.status] ?? p.status}
                </span>
              </div>
              <div className="p-3">
                <p className="line-clamp-2 text-sm font-medium text-zinc-100">{p.title || "Sem título"}</p>
                <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
                  <span>{timeAgo(p.created_at)}</span>
                  {p.counts && (
                    <span className="flex items-center gap-1">
                      <Film className="h-3 w-3" />
                      {(p.counts.scenes ?? 0)} cenas
                    </span>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
