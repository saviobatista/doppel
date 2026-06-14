"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Pencil, Sparkles, Video, X, Check, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  generatePlan,
  getPlan,
  patchPlan,
  subscribePlan,
  subscribeVideo,
} from "@/lib/api";
import type { Bundle, PlanBrief, PlanStatus, Source, VideoPlan } from "@/lib/videoPlan";
import { AgentTimeline } from "./AgentTimeline";
import { ArtifactPanel } from "./ArtifactPanel";
import { ResultView } from "./ResultView";

type Tab = "plan" | "video";

export function AgentScreen({ planId }: { planId: string }) {
  const [brief, setBrief] = useState<PlanBrief | null>(null);
  const [status, setStatus] = useState<PlanStatus>("researching");
  const [buildStep, setBuildStep] = useState<string>("researching");
  const [sources, setSources] = useState<Source[]>([]);
  const [plan, setPlan] = useState<VideoPlan | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  // edit mode
  const [draft, setDraft] = useState<VideoPlan | null>(null);
  const [saving, setSaving] = useState(false);

  // generation
  const [tab, setTab] = useState<Tab>("plan");
  const [videoId, setVideoId] = useState<string | null>(null);
  const [videoStep, setVideoStep] = useState<string | undefined>();
  const [videoStatus, setVideoStatus] = useState<"idle" | "running" | "ready" | "failed">("idle");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  // Snapshot + live build stream.
  useEffect(() => {
    const ac = new AbortController();
    let cancelled = false;
    (async () => {
      try {
        const rec = await getPlan(planId);
        if (cancelled) return;
        setBrief(rec.brief);
        setStatus(rec.status);
        if (rec.plan) setPlan(rec.plan);
        if (rec.bundle) setBundle(rec.bundle);
        if (rec.video_id) {
          setVideoId(rec.video_id);
          setTab("video");
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
        return;
      }
      try {
        await subscribePlan(
          planId,
          (event, data) => {
            if (event === "status") setStatus(data.value as PlanStatus);
            else if (event === "progress") setBuildStep(data.step as string);
            else if (event === "research") setSources((data.sources as Source[]) ?? []);
            else if (event === "plan_partial") setPlan(data.plan as VideoPlan);
            else if (event === "plan") setPlan(data.plan as VideoPlan);
            else if (event === "bundle") setBundle(data.bundle as Bundle);
            else if (event === "audio") {
              // music is generated after `ready` and streams in — merge it
              const tracks = data.audio as VideoPlan["resources"]["audio"];
              setPlan((prev) =>
                prev
                  ? { ...prev, resources: { ...prev.resources, audio: tracks } }
                  : prev,
              );
            } else if (event === "ready") setStatus("ready");
            else if (event === "failed") {
              setStatus("failed");
              setError("A construção do plano falhou.");
            }
          },
          ac.signal,
        );
      } catch {
        /* aborted on unmount */
      }
    })();
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [planId]);

  // Video generation stream (after Generate).
  useEffect(() => {
    if (!videoId) return;
    const ac = new AbortController();
    setVideoStatus("running");
    (async () => {
      try {
        await subscribeVideo(
          videoId,
          (event, data) => {
            if (event === "status") {
              if (data.value === "ready" && data.fast_url) {
                setVideoUrl(data.fast_url as string);
                setVideoStatus("ready");
              } else if (data.value === "failed") {
                setVideoStatus("failed");
              }
            } else if (event === "progress") {
              setVideoStep(data.step as string);
            } else if (event === "fast_ready") {
              setVideoUrl(data.fast_url as string);
              setVideoStatus("ready");
            } else if (event === "failed") {
              setVideoStatus("failed");
              setGenError("A geração do vídeo falhou.");
            }
          },
          ac.signal,
        );
      } catch {
        /* aborted */
      }
    })();
    return () => ac.abort();
  }, [videoId]);

  const onGenerate = useCallback(async () => {
    setGenError(null);
    try {
      const id = await generatePlan(planId);
      setVideoId(id);
      setStatus("generating");
      setTab("video");
    } catch (e) {
      setGenError((e as Error).message);
    }
  }, [planId]);

  const onSave = useCallback(async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const rec = await patchPlan(planId, draft);
      setPlan(rec.plan);
      setDraft(null);
    } catch (e) {
      setGenError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }, [draft, planId]);

  const editing = draft !== null;
  const ready = status === "ready" || status === "generating" || status === "generated";
  const view = editing ? draft : plan;

  return (
    <div className="flex h-dvh min-w-0 flex-1">
      <AgentTimeline
        brief={brief}
        status={status}
        buildStep={buildStep}
        sources={sources}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-white/5 px-6">
          <div className="flex items-center gap-2 min-w-0">
            {videoId && (
              <div className="flex rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
                <TabBtn active={tab === "plan"} onClick={() => setTab("plan")}>
                  Plano
                </TabBtn>
                <TabBtn active={tab === "video"} onClick={() => setTab("video")}>
                  Vídeo
                </TabBtn>
              </div>
            )}
            <h1 className="truncate text-sm font-medium text-zinc-300">
              {view?.title ?? "Montando seu plano de vídeo…"}
            </h1>
          </div>

          <div className="flex items-center gap-2">
            {editing ? (
              <>
                <button
                  onClick={() => setDraft(null)}
                  className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-sm text-zinc-300 hover:bg-white/10"
                >
                  <X className="h-4 w-4" />
                  Cancelar
                </button>
                <button
                  onClick={onSave}
                  disabled={saving}
                  className="flex items-center gap-1.5 rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-obsidian hover:bg-accent-strong disabled:opacity-60"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Salvar
                </button>
              </>
            ) : (
              ready &&
              tab === "plan" &&
              view && (
                <>
                  <button
                    onClick={() => setDraft(structuredClone(view))}
                    className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-sm text-zinc-200 hover:bg-white/10"
                  >
                    <Pencil className="h-4 w-4" />
                    Editar
                  </button>
                  <button
                    onClick={onGenerate}
                    disabled={status === "generating"}
                    className="flex items-center gap-1.5 rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-obsidian hover:bg-accent-strong disabled:opacity-60"
                  >
                    {status === "generating" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                    Gerar vídeo
                  </button>
                </>
              )
            )}
          </div>
        </header>

        {/* Body */}
        <main className="flex-1 overflow-y-auto">
          {error && (
            <div className="mx-auto mt-10 flex max-w-md items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              <AlertTriangle className="h-4 w-4" />
              {error}
            </div>
          )}
          {genError && (
            <div className="mx-auto mt-4 flex max-w-2xl items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-200">
              <AlertTriangle className="h-4 w-4" />
              {genError}
            </div>
          )}

          {tab === "video" && videoId ? (
            <ResultView
              plan={plan}
              status={videoStatus}
              step={videoStep}
              videoUrl={videoUrl}
            />
          ) : (
            <ArtifactPanel
              plan={view}
              bundle={bundle}
              editing={editing}
              onChange={setDraft}
              building={!ready && !error}
              buildStep={buildStep}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 font-medium transition-colors",
        active ? "bg-accent text-obsidian" : "text-zinc-400 hover:text-zinc-200",
      )}
    >
      {children}
    </button>
  );
}
