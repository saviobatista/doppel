"use client";

import { Download, Loader2, Sparkles, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";
import type { VideoPlan } from "@/lib/videoPlan";
import { SCENE_KIND, videoStepLabel } from "./labels";

export function ResultView({
  plan,
  status,
  step,
  videoUrl,
}: {
  plan: VideoPlan | null;
  status: "idle" | "running" | "ready" | "failed";
  step: string | undefined;
  videoUrl: string | null;
}) {
  const scenes = plan?.script.scenes ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-6">
      <div className="overflow-hidden rounded-3xl border border-white/10 bg-panel">
        {/* Stage */}
        <div className="relative flex min-h-[420px] items-center justify-center bg-black p-4">
          {status === "ready" && videoUrl ? (
            <video
              src={videoUrl}
              controls
              autoPlay
              playsInline
              className="max-h-[70vh] rounded-xl"
            />
          ) : status === "failed" ? (
            <div className="flex flex-col items-center gap-2 text-center text-red-300">
              <AlertTriangle className="h-8 w-8" />
              <p className="text-sm">A geração falhou. Tente gerar novamente.</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="relative flex h-16 w-16 items-center justify-center">
                <span className="absolute inset-0 animate-ping rounded-full bg-accent/20" />
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/15 text-accent ring-1 ring-accent/30">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </span>
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-200">{videoStepLabel(step)}</p>
                <p className="mt-1 text-xs text-zinc-500">
                  Gerando avatar, cenas e legendas — isso leva ~1 minuto.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Title + actions */}
        <div className="flex items-center justify-between gap-3 border-t border-white/5 px-5 py-3">
          <div className="flex items-center gap-2 min-w-0">
            <Sparkles className="h-4 w-4 shrink-0 text-accent" />
            <span className="truncate text-sm font-medium text-zinc-200">
              {plan?.title ?? "Seu vídeo"}
            </span>
          </div>
          {status === "ready" && videoUrl && (
            <a
              href={videoUrl}
              download
              className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-white/10"
            >
              <Download className="h-3.5 w-3.5" />
              Baixar
            </a>
          )}
        </div>
      </div>

      {/* Scene timeline */}
      {scenes.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Linha do tempo · {scenes.length} cenas
          </p>
          <div className="flex gap-2 overflow-x-auto pb-2">
            {scenes.map((scene, i) => {
              const kind = SCENE_KIND[scene.kind] ?? SCENE_KIND.avatar;
              const KindIcon = kind.icon;
              return (
                <div
                  key={scene.id}
                  className="flex w-32 shrink-0 flex-col gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] p-2.5"
                >
                  <div className="flex aspect-video items-center justify-center rounded-lg bg-gradient-to-br from-white/10 to-white/[0.02]">
                    <KindIcon className={cn("h-5 w-5", kind.text)} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-zinc-300">Cena {i + 1}</span>
                    <span className="text-[10px] text-zinc-600">{scene.duration_seconds}s</span>
                  </div>
                  <span className="truncate text-[11px] text-zinc-500">{scene.title}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
