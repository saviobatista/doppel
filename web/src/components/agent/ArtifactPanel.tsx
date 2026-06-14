"use client";

import {
  ArrowDown,
  Clock,
  Coins,
  Compass,
  Download,
  Film,
  Globe,
  Languages,
  Lightbulb,
  Monitor,
  Music,
  Package,
  Play,
  Smartphone,
  Sparkles,
  Video,
  Volume2,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import type { Bundle, Scene, VideoPlan } from "@/lib/videoPlan";
import { overlayIcon, SCENE_KIND, transitionLabel } from "./labels";

export function ArtifactPanel({
  plan,
  bundle,
  editing,
  onChange,
  building,
  buildStep,
}: {
  plan: VideoPlan | null;
  bundle?: Bundle | null;
  editing: boolean;
  onChange: (plan: VideoPlan) => void;
  building: boolean;
  buildStep: string;
}) {
  if (!plan) return <BuildingSkeleton step={buildStep} building={building} />;

  const update = (patch: Partial<VideoPlan>) => onChange({ ...plan, ...patch });
  const updateScene = (i: number, patch: Partial<Scene>) => {
    const scenes = (plan.script?.scenes ?? []).map((s, idx) =>
      idx === i ? { ...s, ...patch } : s,
    );
    onChange({ ...plan, script: { ...plan.script, scenes } });
  };

  const meta = plan.meta ?? {};
  const scenes = plan.script?.scenes ?? [];
  const tracks = plan.resources?.audio ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-6">
      {/* Hero */}
      <section className="overflow-hidden rounded-3xl border border-white/10 bg-panel">
        <div className="relative h-28 bg-gradient-to-br from-accent/30 via-neon-purple/20 to-transparent">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_120%_at_30%_0%,rgba(56,189,248,0.25),transparent_70%)]" />
        </div>
        <div className="-mt-10 px-6 pb-6">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-obsidian/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-accent ring-1 ring-accent/30 backdrop-blur">
            <Film className="h-3.5 w-3.5" />
            Plano de vídeo
          </span>
          {editing ? (
            <input
              value={plan.title}
              onChange={(e) => update({ title: e.target.value })}
              className="mt-3 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-2xl font-bold text-white focus:border-accent/40 focus:outline-none"
            />
          ) : (
            <h2 className="mt-3 text-2xl font-bold text-white">{plan.title}</h2>
          )}
          {(plan.logline || editing) &&
            (editing ? (
              <textarea
                value={plan.logline ?? ""}
                onChange={(e) => update({ logline: e.target.value })}
                rows={2}
                placeholder="Logline"
                className="mt-2 w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-zinc-300 focus:border-accent/40 focus:outline-none"
              />
            ) : (
              <p className="mt-1.5 text-sm text-zinc-400">{plan.logline}</p>
            ))}

          <div className="mt-4 flex flex-wrap gap-2">
            <MetaChip icon={Clock} label={`${meta.duration_seconds ?? "—"}s`} />
            <MetaChip
              icon={meta.orientation === "landscape" ? Monitor : Smartphone}
              label={meta.orientation === "landscape" ? "Paisagem" : "Retrato 9:16"}
            />
            <MetaChip icon={Languages} label={meta.language ?? "pt-BR"} />
            {meta.credits_estimate && (
              <MetaChip icon={Coins} label={`${meta.credits_estimate} créditos`} accent />
            )}
          </div>
        </div>
      </section>

      {/* Persisted artifact bundle */}
      {bundle && !editing && (
        <section className="mt-4 flex items-center gap-3 rounded-2xl border border-neon-green/20 bg-neon-green/[0.06] p-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-neon-green/15 text-neon-green ring-1 ring-neon-green/30">
            <Package className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-white">Artefato salvo da sessão</p>
            <p className="truncate text-xs text-zinc-400">
              {bundle.counts &&
                ["scenes", "media", "overlays", "audio", "footage"]
                  .filter((k) => (bundle.counts?.[k] ?? 0) > 0)
                  .map((k) => `${bundle.counts?.[k]} ${k}`)
                  .join(" · ")}
            </p>
          </div>
          {bundle.plan_download_url && (
            <a
              href={bundle.plan_download_url}
              target="_blank"
              rel="noreferrer"
              className="flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-white/10"
            >
              <Download className="h-3.5 w-3.5" />
              plan.json
            </a>
          )}
        </section>
      )}

      {/* Style */}
      <Section icon={Sparkles} title="Estilo">
        {editing ? (
          <textarea
            value={plan.style}
            onChange={(e) => update({ style: e.target.value })}
            rows={2}
            className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-zinc-300 focus:border-accent/40 focus:outline-none"
          />
        ) : (
          <p className="text-sm text-zinc-300">{plan.style}</p>
        )}
      </Section>

      {/* Research */}
      {plan.research && (
        <Section icon={Compass} title="Pesquisa">
          {plan.research.angle && (
            <div className="mb-3 flex gap-2 rounded-xl border border-accent/20 bg-accent/5 px-3 py-2.5">
              <Lightbulb className="h-4 w-4 shrink-0 text-accent" />
              <p className="text-sm text-zinc-200">{plan.research.angle}</p>
            </div>
          )}
          <p className="text-sm text-zinc-400">{plan.research.summary}</p>
          {plan.research.key_points?.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {plan.research.key_points.map((kp, i) => (
                <li key={i} className="flex gap-2 text-sm text-zinc-300">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {kp}
                </li>
              ))}
            </ul>
          )}
          {plan.research.sources && plan.research.sources.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {plan.research.sources.slice(0, 8).map((s, i) => (
                <a
                  key={`${s.url}-${i}`}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex max-w-[220px] items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-zinc-400 hover:border-accent/30 hover:text-accent"
                >
                  <Globe className="h-3 w-3 shrink-0" />
                  <span className="truncate">{s.title}</span>
                </a>
              ))}
            </div>
          )}
        </Section>
      )}

      {/* Script + direction + transitions */}
      <Section icon={Film} title={`Roteiro · ${scenes.length} cenas`}>
        <div className="space-y-1">
          {scenes.map((scene, i) => (
            <div key={scene.id}>
              <SceneCard
                scene={scene}
                index={i}
                editing={editing}
                onChange={(patch) => updateScene(i, patch)}
              />
              {scene.transition_out && i < scenes.length - 1 && (
                <div className="flex items-center justify-center gap-1.5 py-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-600">
                  <ArrowDown className="h-3 w-3" />
                  {transitionLabel[scene.transition_out.type] ?? scene.transition_out.type}
                  {scene.transition_out.duration_seconds
                    ? ` · ${scene.transition_out.duration_seconds}s`
                    : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* Audio */}
      {plan.audio?.music && (
        <Section icon={Volume2} title="Áudio">
          {/* Background music — info header + the playable generated versions, as one block */}
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Trilha de fundo
          </p>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-neon-purple/15 text-neon-purple">
                <Music className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-zinc-100">
                  {plan.audio.music.title}
                </p>
                <p className="truncate text-xs text-zinc-500">{plan.audio.music.mood}</p>
              </div>
              {plan.audio.music.bpm && (
                <span className="shrink-0 rounded-full bg-white/5 px-2 py-0.5 text-xs text-zinc-400">
                  {plan.audio.music.bpm} BPM
                </span>
              )}
            </div>

            {tracks.length > 0 ? (
              <div className="mt-3 space-y-3 border-t border-white/5 pt-3">
                <p className="text-[11px] text-zinc-500">
                  {tracks.length > 1
                    ? `Compare ${tracks.length} versões geradas`
                    : "Versão gerada"}
                </p>
                {tracks.map((t) => (
                  <div key={t.source}>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="truncate text-xs text-zinc-300">{t.label}</span>
                      <span className="ml-auto shrink-0 rounded-full bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
                        {t.source}
                      </span>
                    </div>
                    {t.preview_url ? (
                      <audio src={t.preview_url} controls preload="none" className="h-9 w-full" />
                    ) : (
                      <p className="text-[11px] text-zinc-600">indisponível</p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 border-t border-white/5 pt-3 text-[11px] text-zinc-500">
                Gerando trilha de fundo…
              </p>
            )}
          </div>

          {plan.audio.sfx && plan.audio.sfx.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Efeitos sonoros · {plan.audio.sfx.length}
              </p>
              <div className="space-y-1">
                {plan.audio.sfx.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm text-zinc-400">
                    <Waves className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                    <span>{s.cue}</span>
                    {s.at_scene && <span className="text-xs text-zinc-600">({s.at_scene})</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(plan.audio.ducking || plan.audio.voiceover?.tone) && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {plan.audio.voiceover?.tone && (
                <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-zinc-400">
                  Tom: {plan.audio.voiceover.tone}
                </span>
              )}
              {plan.audio.ducking && (
                <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-zinc-400">
                  Ducking ativo
                </span>
              )}
            </div>
          )}
        </Section>
      )}

      {/* Resources */}
      {plan.resources && (
        <Section icon={Sparkles} title="Recursos">
          {plan.resources.design_elements && plan.resources.design_elements.length > 0 && (
            <>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Elementos de design · {plan.resources.design_elements.length}
              </p>
              <div className="mb-4 grid grid-cols-2 gap-2">
                {plan.resources.design_elements.map((d) => {
                  const Icon = overlayIcon(d.kind);
                  return d.preview_url ? (
                    <a
                      key={d.id}
                      href={d.preview_url}
                      target="_blank"
                      rel="noreferrer"
                      className="group overflow-hidden rounded-xl border border-white/10 bg-black/40 transition-colors hover:border-accent/40"
                    >
                      <div className="flex items-center justify-center p-2.5">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={d.preview_url}
                          alt={d.label}
                          className="max-h-20 w-full object-contain"
                        />
                      </div>
                      <div className="flex items-center gap-1.5 border-t border-white/5 px-2.5 py-1.5">
                        <Icon className="h-3 w-3 shrink-0 text-accent" />
                        <span className="truncate text-[11px] text-zinc-400">{d.label}</span>
                      </div>
                    </a>
                  ) : (
                    <span
                      key={d.id}
                      className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-zinc-300"
                    >
                      <Icon className="h-3.5 w-3.5 text-accent" />
                      {d.label}
                    </span>
                  );
                })}
              </div>
            </>
          )}
          {plan.resources.media && plan.resources.media.length > 0 && (
            <>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Mídia · {plan.resources.media.length}
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {plan.resources.media.map((m, i) => {
                  const badge =
                    m.source === "scraped" || m.source === "youtube" ? "Real" : null;
                  if (m.kind === "video" && m.video_url) {
                    return (
                      <div
                        key={i}
                        className="overflow-hidden rounded-xl border border-white/10 bg-black/40"
                      >
                        <video
                          src={m.video_url}
                          poster={m.preview_url}
                          controls
                          playsInline
                          preload="none"
                          className="aspect-[9/16] w-full bg-black object-cover"
                        />
                        <div className="flex items-center gap-1.5 px-2 py-1.5">
                          <Film className="h-3 w-3 shrink-0 text-neon-purple" />
                          <span className="truncate text-[11px] text-zinc-400">{m.label}</span>
                          {badge && (
                            <span className="ml-auto rounded bg-neon-green/15 px-1 text-[9px] font-semibold text-neon-green">
                              {badge}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  }
                  return m.preview_url ? (
                    <a
                      key={i}
                      href={m.preview_url}
                      target="_blank"
                      rel="noreferrer"
                      className="group overflow-hidden rounded-xl border border-white/10 bg-black/40 transition-colors hover:border-accent/40"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={m.preview_url}
                        alt={m.label}
                        className="aspect-[9/16] w-full object-cover"
                      />
                      <div className="flex items-center gap-1.5 px-2 py-1.5">
                        <Film className="h-3 w-3 shrink-0 text-neon-purple" />
                        <span className="truncate text-[11px] text-zinc-400">{m.label}</span>
                        {badge && (
                          <span className="ml-auto rounded bg-neon-green/15 px-1 text-[9px] font-semibold text-neon-green">
                            {badge}
                          </span>
                        )}
                      </div>
                    </a>
                  ) : (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1.5"
                    >
                      <Film className="h-3.5 w-3.5 shrink-0 text-neon-purple" />
                      <span className="truncate text-sm text-zinc-300">{m.label}</span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
          {plan.resources.footage && plan.resources.footage.length > 0 && (
            <>
              <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Vídeos relacionados · YouTube
              </p>
              <div className="grid grid-cols-2 gap-2">
                {plan.resources.footage.map((v, i) => (
                  <a
                    key={i}
                    href={v.source_link ?? v.video_url}
                    target="_blank"
                    rel="noreferrer"
                    className="group overflow-hidden rounded-xl border border-white/10 bg-black/40 transition-colors hover:border-accent/40"
                  >
                    <div className="relative">
                      {v.preview_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={v.preview_url}
                          alt={v.label}
                          className="aspect-video w-full object-cover"
                        />
                      ) : (
                        <div className="flex aspect-video w-full items-center justify-center bg-white/[0.03]">
                          <Video className="h-6 w-6 text-zinc-600" />
                        </div>
                      )}
                      <span className="absolute inset-0 flex items-center justify-center">
                        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-black/60 ring-1 ring-white/20 transition-colors group-hover:bg-accent group-hover:text-obsidian">
                          <Play className="ml-0.5 h-4 w-4" />
                        </span>
                      </span>
                      {v.length && (
                        <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1 text-[10px] font-medium text-white">
                          {v.length}
                        </span>
                      )}
                    </div>
                    <div className="px-2 py-1.5">
                      <p className="line-clamp-2 text-[11px] text-zinc-300">{v.label}</p>
                      <p className="mt-0.5 truncate text-[10px] text-zinc-500">
                        {[v.channel, v.published].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                  </a>
                ))}
              </div>
            </>
          )}
        </Section>
      )}
    </div>
  );
}

function SceneCard({
  scene,
  index,
  editing,
  onChange,
}: {
  scene: Scene;
  index: number;
  editing: boolean;
  onChange: (patch: Partial<Scene>) => void;
}) {
  const kind = SCENE_KIND[scene.kind] ?? SCENE_KIND.avatar;
  const KindIcon = kind.icon;
  const d = scene.direction ?? { shot: "", mood: "" };
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/5 text-xs font-semibold text-zinc-400">
          {index + 1}
        </span>
        <span
          className={cn(
            "flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-[11px] font-medium ring-1",
            kind.ring,
            kind.text,
          )}
        >
          <KindIcon className="h-3 w-3" />
          {kind.label}
        </span>
        <span className="text-sm font-medium text-zinc-200">{scene.title}</span>
        <span className="ml-auto text-xs text-zinc-600">{scene.duration_seconds}s</span>
      </div>

      {(scene.on_screen_text || editing) && (
        <div className="mt-2.5">
          {editing ? (
            <input
              value={scene.on_screen_text ?? ""}
              onChange={(e) => onChange({ on_screen_text: e.target.value })}
              placeholder="Texto na tela"
              className="w-full rounded-md border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wide text-accent focus:border-accent/40 focus:outline-none"
            />
          ) : (
            scene.on_screen_text && (
              <span className="inline-block rounded-md bg-accent/10 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-accent ring-1 ring-accent/20">
                {scene.on_screen_text}
              </span>
            )
          )}
        </div>
      )}

      {(scene.narration || editing) && (
        <div className="mt-2.5">
          {editing ? (
            <textarea
              value={scene.narration ?? ""}
              onChange={(e) => onChange({ narration: e.target.value })}
              rows={2}
              placeholder="Narração"
              className="w-full resize-none rounded-md border border-white/10 bg-white/5 px-2.5 py-2 text-sm text-zinc-300 focus:border-accent/40 focus:outline-none"
            />
          ) : (
            <p className="text-sm leading-relaxed text-zinc-300">{scene.narration}</p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {d.shot && <DirTag label={d.shot} />}
        {d.camera && <DirTag label={d.camera} />}
        {d.mood && <DirTag label={d.mood} />}
        {d.framing && <DirTag label={d.framing} muted />}
      </div>
      {d.b_roll_prompt && !editing && (
        <p className="mt-2 line-clamp-2 text-xs italic text-zinc-500">{d.b_roll_prompt}</p>
      )}
      {scene.overlays && scene.overlays.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {scene.overlays.map((ov) => (
            <span
              key={ov}
              className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-500"
            >
              {ov}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function DirTag({ label, muted }: { label: string; muted?: boolean }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px] capitalize",
        muted ? "bg-white/[0.03] text-zinc-500" : "bg-white/5 text-zinc-400",
      )}
    >
      {label}
    </span>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4 rounded-3xl border border-white/10 bg-panel p-5">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
        <Icon className="h-4 w-4 text-accent" />
        {title}
      </h3>
      {children}
    </section>
  );
}

function MetaChip({
  icon: Icon,
  label,
  accent,
}: {
  icon: LucideIcon;
  label: string;
  accent?: boolean;
}) {
  return (
    <span
      className={cn(
        "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1",
        accent
          ? "bg-accent/10 text-accent ring-accent/30"
          : "bg-white/5 text-zinc-300 ring-white/10",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}

function BuildingSkeleton({ step, building }: { step: string; building: boolean }) {
  const label =
    step === "researching"
      ? "Pesquisando o tema na web…"
      : step === "scripting"
        ? "Escrevendo roteiro, direção e áudio…"
        : "Montando o plano…";
  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-10">
      {building && (
        <div className="mb-6 flex items-center gap-2 text-sm text-zinc-400">
          <Sparkles className="h-4 w-4 animate-pulse text-accent" />
          {label}
        </div>
      )}
      <div className="space-y-4">
        <div className="h-28 animate-pulse rounded-3xl bg-white/[0.04]" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-2 rounded-3xl border border-white/10 bg-panel p-5">
            <div className="h-4 w-1/3 animate-pulse rounded bg-white/10" />
            <div className="h-3 w-full animate-pulse rounded bg-white/5" />
            <div className="h-3 w-4/5 animate-pulse rounded bg-white/5" />
          </div>
        ))}
      </div>
    </div>
  );
}
