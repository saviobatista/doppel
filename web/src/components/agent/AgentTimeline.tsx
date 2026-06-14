"use client";

import {
  AudioLines,
  Check,
  Globe,
  Layers,
  Loader2,
  PenLine,
  Search,
  Sparkles,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import type { PlanBrief, PlanStatus, Source } from "@/lib/videoPlan";

type PhaseState = "pending" | "active" | "done";

function domain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function AgentTimeline({
  brief,
  status,
  buildStep,
  sources,
}: {
  brief: PlanBrief | null;
  status: PlanStatus;
  buildStep: string;
  sources: Source[];
}) {
  // Phases reflect the real build STAGE (buildStep/status), not whether a partial
  // plan has streamed in — otherwise progressive fill would falsely mark steps done.
  const complete = ["ready", "generating", "generated"].includes(status);
  const failed = status === "failed";
  const afterResearch = complete || ["scripting", "rendering_assets"].includes(buildStep);
  const afterScripting = complete || buildStep === "rendering_assets";

  const researchState: PhaseState = afterResearch || sources.length > 0
    ? "done"
    : failed
      ? "pending"
      : "active";
  const scriptState: PhaseState = afterScripting
    ? "done"
    : buildStep === "scripting" && !failed
      ? "active"
      : "pending";
  const assetsState: PhaseState = complete
    ? "done"
    : buildStep === "rendering_assets" && !failed
      ? "active"
      : "pending";

  return (
    <aside className="hidden w-[380px] shrink-0 flex-col border-r border-white/5 bg-panel/40 md:flex">
      <div className="flex items-center gap-2 border-b border-white/5 px-5 py-4">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/15 text-accent ring-1 ring-accent/30">
          <Sparkles className="h-4 w-4" />
        </span>
        <span className="text-sm font-semibold text-white">Agente de Vídeo</span>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        {/* User request */}
        {brief && (
          <div className="ml-auto max-w-[90%]">
            <div className="rounded-2xl rounded-tr-sm bg-accent/15 px-4 py-3 text-sm text-zinc-100 ring-1 ring-accent/20">
              {brief.prompt}
            </div>
            <div className="mt-2 flex flex-wrap justify-end gap-1.5">
              <Chip icon={UserRound} label={brief.avatar_label || "Avatar automático"} />
              <Chip icon={AudioLines} label={brief.voice_label || "Voz automática"} />
            </div>
          </div>
        )}

        {/* Agent run */}
        <div className="flex gap-2.5">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/5 text-accent ring-1 ring-white/10">
            <Sparkles className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1 space-y-3">
            <p className="text-sm text-zinc-300">
              {complete
                ? "Pronto! Montei seu plano de vídeo com pesquisa, roteiro, direção, áudio e recursos. Revise à direita e gere quando quiser."
                : "Vou pesquisar o tema e montar um plano de vídeo completo para você."}
            </p>

            <div className="space-y-1.5">
              <Phase icon={Search} state={researchState} label="Pesquisando na web" />
              {sources.length > 0 && (
                <div className="ml-9 space-y-1 border-l border-white/10 pl-3">
                  {sources.slice(0, 6).map((s, i) => (
                    <a
                      key={`${s.url}-${i}`}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1.5 truncate text-xs text-zinc-500 hover:text-accent"
                    >
                      <Globe className="h-3 w-3 shrink-0" />
                      <span className="truncate">{domain(s.url)}</span>
                    </a>
                  ))}
                  {sources.length > 6 && (
                    <span className="text-xs text-zinc-600">+{sources.length - 6} fontes</span>
                  )}
                </div>
              )}
              <Phase icon={PenLine} state={scriptState} label="Roteiro, direção e áudio" />
              <Phase icon={Layers} state={assetsState} label="Gerando prévias dos recursos" />
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function Phase({ icon: Icon, state, label }: { icon: LucideIcon; state: PhaseState; label: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={cn(
          "flex h-6 w-6 items-center justify-center rounded-full ring-1 transition-colors",
          state === "done" && "bg-accent/15 text-accent ring-accent/30",
          state === "active" && "bg-white/5 text-accent ring-white/10",
          state === "pending" && "bg-white/[0.02] text-zinc-600 ring-white/5",
        )}
      >
        {state === "done" ? (
          <Check className="h-3.5 w-3.5" strokeWidth={3} />
        ) : state === "active" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Icon className="h-3.5 w-3.5" />
        )}
      </span>
      <span
        className={cn(
          "text-sm",
          state === "pending" ? "text-zinc-600" : "text-zinc-200",
        )}
      >
        {label}
      </span>
    </div>
  );
}

function Chip({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-zinc-300">
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}
