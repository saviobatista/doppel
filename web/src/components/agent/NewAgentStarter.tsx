"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, Clock, Loader2, Monitor, Smartphone, Sparkles, UserRound } from "lucide-react";
import { cn } from "@/lib/cn";
import { Dropdown } from "@/components/ui/Dropdown";
import { createPlan, listAvatars, type AvatarItem } from "@/lib/api";

const DURATIONS = [
  { value: "15", label: "15s" },
  { value: "30", label: "30s" },
  { value: "40", label: "40s" },
  { value: "60", label: "60s" },
];

const ORIENTATIONS = [
  { value: "portrait", label: "Retrato 9:16" },
  { value: "landscape", label: "Paisagem 16:9" },
];

export function NewAgentStarter({
  initialPrompt = "",
  initialAvatarId = "",
}: {
  initialPrompt?: string;
  initialAvatarId?: string;
}) {
  const router = useRouter();
  const [prompt, setPrompt] = useState(initialPrompt);
  const [avatars, setAvatars] = useState<AvatarItem[]>([]);
  const [avatarId, setAvatarId] = useState(initialAvatarId);
  const [duration, setDuration] = useState("40");
  const [orientation, setOrientation] = useState("portrait");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAvatars()
      .then((list) => {
        const ready = list.filter((a) => a.status === "ready");
        setAvatars(ready);
        // Honor a pre-selected avatar (from "Criar vídeo" on a card/looks screen)
        // when it's ready; otherwise fall back to the first available.
        setAvatarId((cur) => {
          if (cur && ready.some((a) => a.avatar_id === cur)) return cur;
          return ready[0]?.avatar_id ?? "";
        });
      })
      .catch(() => setAvatars([]));
  }, []);

  const avatarOptions = avatars.map((a, i) => ({
    value: a.avatar_id,
    label: a.label?.trim() || `Avatar ${i + 1}`,
  }));

  async function submit() {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const avatarLabel = avatarOptions.find((o) => o.value === avatarId)?.label;
      const planId = await createPlan({
        prompt: prompt.trim(),
        avatar_id: avatarId || null,
        avatar_label: avatarLabel ?? "Avatar",
        voice_label: avatarLabel ?? "Voz",
        duration_seconds: Number(duration),
        orientation,
        language: "pt-BR",
      });
      router.push(`/agente/${planId}`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-16">
      <div className="flex flex-col items-center text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/15 text-accent ring-1 ring-accent/30">
          <Sparkles className="h-6 w-6" />
        </span>
        <h1 className="mt-4 text-3xl font-bold text-white">Agente de Vídeo</h1>
        <p className="mt-2 text-sm text-zinc-400">
          Descreva o vídeo. O agente pesquisa, roteiriza, dirige e monta o plano completo para você
          revisar e gerar.
        </p>
      </div>

      <div className="mt-8 rounded-3xl border border-white/10 bg-white/[0.04] p-3 shadow-2xl shadow-black/40">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
          }}
          rows={3}
          autoFocus
          placeholder="Ex.: Um podcast curto e energético sobre o jogo do Brasil de hoje na Copa"
          className="w-full resize-none bg-transparent px-2 pt-1 text-[15px] text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            <Dropdown
              value={avatarId}
              options={avatarOptions}
              onChange={setAvatarId}
              icon={UserRound}
              placeholder="Avatar automático"
              emptyLabel="Nenhum avatar pronto"
            />
            <Dropdown value={duration} options={DURATIONS} onChange={setDuration} icon={Clock} />
            <Dropdown
              value={orientation}
              options={ORIENTATIONS}
              onChange={setOrientation}
              icon={orientation === "landscape" ? Monitor : Smartphone}
            />
          </div>
          <button
            onClick={submit}
            disabled={!prompt.trim() || submitting}
            className={cn(
              "flex h-9 items-center gap-1.5 rounded-full px-4 text-sm font-semibold transition-all",
              prompt.trim() && !submitting
                ? "bg-accent text-obsidian hover:bg-accent-strong"
                : "cursor-not-allowed bg-white/10 text-zinc-500",
            )}
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            Criar plano
          </button>
        </div>
      </div>

      {avatars.length === 0 && (
        <p className="mt-3 text-center text-xs text-zinc-500">
          Dica: crie um avatar em <span className="text-zinc-300">Avatar → Novo Avatar</span> para
          poder gerar o vídeo ao final.
        </p>
      )}
      {error && <p className="mt-3 text-center text-sm text-red-300">{error}</p>}
    </div>
  );
}
