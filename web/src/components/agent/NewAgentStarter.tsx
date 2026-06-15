"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUp, ChevronDown, Clock, Loader2, Mic, Monitor, Pause, Play, Smartphone,
  Sparkles, UserRound,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { Dropdown } from "@/components/ui/Dropdown";
import { AvatarPickerModal } from "@/components/agent/AvatarPickerModal";
import { VoicePickerModal } from "@/components/agent/VoicePickerModal";
import {
  createPlan, getVoicePreview, listAvatars, listVoices, type AvatarItem, type VoiceSummary,
} from "@/lib/api";

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

/** Encode an avatar (+ optional look index) into a single picker value. */
function pickerValue(avatarId: string, lookIndex?: number | null): string {
  return lookIndex == null ? avatarId : `${avatarId}#${lookIndex}`;
}

export function NewAgentStarter({
  initialPrompt = "",
  initialAvatarId = "",
  initialLook = null,
}: {
  initialPrompt?: string;
  initialAvatarId?: string;
  initialLook?: number | null;
}) {
  const router = useRouter();
  const [prompt, setPrompt] = useState(initialPrompt);
  const [avatars, setAvatars] = useState<AvatarItem[]>([]);
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [selection, setSelection] = useState(
    initialAvatarId ? pickerValue(initialAvatarId, initialLook) : "",
  );
  const [voiceId, setVoiceId] = useState("");
  const [voiceLabel, setVoiceLabel] = useState("Voz do avatar");
  const [duration, setDuration] = useState("40");
  const [orientation, setOrientation] = useState("portrait");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [avatarModal, setAvatarModal] = useState(false);
  const [voiceModal, setVoiceModal] = useState(false);

  // --- Selected avatar / look display ---
  const [selAvatarId, lookStr] = selection.split("#");
  const lookIndex = lookStr != null ? Number(lookStr) : null;
  const selAvatar = avatars.find((a) => a.avatar_id === selAvatarId);
  const avatarName = selAvatar?.label?.trim() || "Avatar automático";
  const selLook = lookIndex != null ? selAvatar?.looks?.[lookIndex] : null;
  const avatarThumb = selLook?.url ?? selAvatar?.preview_url ?? null;
  const avatarSub = selLook
    ? selLook.label?.trim() || `Visual ${(lookIndex ?? 0) + 1}`
    : "Avatar";

  // --- Voice preview playback for the voice card ---
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [voicePlaying, setVoicePlaying] = useState(false);

  useEffect(() => {
    listAvatars()
      .then((list) => {
        const ready = list.filter((a) => a.status === "ready");
        setAvatars(ready);
        // Keep a valid pre-selection (from "Criar vídeo"/"Usar no vídeo"); else
        // fall back to the first ready avatar's base look.
        setSelection((cur) => {
          const valid = ready.some((a) => {
            const [aid, look] = cur.split("#");
            if (a.avatar_id !== aid) return false;
            return look == null || Number(look) < (a.looks?.length ?? 0);
          });
          if (cur && valid) return cur;
          return ready[0]?.avatar_id ?? "";
        });
      })
      .catch(() => setAvatars([]));
    listVoices()
      .then((list) => setVoices(list.filter((v) => v.status === "ready")))
      .catch(() => setVoices([]));
  }, []);

  useEffect(() => {
    const a = audioRef.current;
    return () => a?.pause();
  }, []);

  // Stop playback whenever the selected voice changes.
  useEffect(() => {
    audioRef.current?.pause();
    setVoicePlaying(false);
  }, [voiceId]);

  async function toggleVoicePreview() {
    if (!voiceId) return;
    if (voicePlaying) {
      audioRef.current?.pause();
      setVoicePlaying(false);
      return;
    }
    try {
      const url = await getVoicePreview(voiceId);
      if (!url) return;
      if (!audioRef.current) audioRef.current = new Audio();
      audioRef.current.src = url;
      audioRef.current.onended = () => setVoicePlaying(false);
      await audioRef.current.play();
      setVoicePlaying(true);
    } catch {
      setVoicePlaying(false);
    }
  }

  async function submit() {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const lookLabel = selLook?.label?.trim() ?? null;
      const planId = await createPlan({
        prompt: prompt.trim(),
        avatar_id: selAvatarId || null,
        avatar_label: selAvatar?.label?.trim() || "Avatar",
        voice_id: voiceId || null,
        voice_label: voiceId ? voiceLabel : selAvatar?.label?.trim() || "Avatar",
        look_index: lookIndex,
        look_label: lookLabel,
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
    <div className="mx-auto w-full max-w-3xl px-6 py-16">
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
        <div className="flex flex-wrap items-center gap-2 px-1 pb-1 pt-1">
          {/* Avatar selector card — opens the grid/list picker. */}
          <button
            type="button"
            onClick={() => setAvatarModal(true)}
            className="flex items-center gap-2.5 rounded-full border border-white/10 bg-white/5 py-1 pl-1 pr-3 text-left transition-colors hover:border-white/25 hover:bg-white/10"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/5">
              {avatarThumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={avatarThumb} alt="" className="h-full w-full object-cover" />
              ) : (
                <UserRound className="h-4 w-4 text-zinc-400" />
              )}
            </span>
            <span className="min-w-0">
              <span className="block max-w-[140px] truncate text-sm font-semibold text-white">
                {avatarName}
              </span>
              <span className="block text-[11px] text-zinc-500">{avatarSub}</span>
            </span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
          </button>

          {/* Voice selector card — name + play, opens the voice picker. */}
          <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 py-1 pl-1 pr-2 transition-colors hover:border-white/25">
            <button
              type="button"
              onClick={toggleVoicePreview}
              disabled={!voiceId}
              aria-label="Ouvir voz"
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors",
                voiceId
                  ? "bg-accent/20 text-accent hover:bg-accent/30"
                  : "bg-white/5 text-zinc-600",
              )}
            >
              {voicePlaying ? (
                <Pause className="h-4 w-4" />
              ) : voiceId ? (
                <Play className="h-4 w-4 translate-x-px" />
              ) : (
                <Mic className="h-4 w-4" />
              )}
            </button>
            <button
              type="button"
              onClick={() => setVoiceModal(true)}
              className="flex items-center gap-2 text-left"
            >
              <span className="min-w-0">
                <span className="block max-w-[140px] truncate text-sm font-semibold text-white">
                  {voiceId ? voiceLabel : "Voz do avatar"}
                </span>
                <span className="block text-[11px] text-zinc-500">Voz</span>
              </span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
            </button>
          </div>
        </div>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
          }}
          rows={3}
          autoFocus
          placeholder="Ex.: Um podcast curto e energético sobre o jogo do Brasil de hoje na Copa"
          className="mt-1 w-full resize-none bg-transparent px-2 pt-1 text-[15px] text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
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

      {avatarModal && (
        <AvatarPickerModal
          avatars={avatars}
          value={selection}
          onSelect={(aid, look) => setSelection(pickerValue(aid, look))}
          onClose={() => setAvatarModal(false)}
        />
      )}
      {voiceModal && (
        <VoicePickerModal
          voices={voices}
          value={voiceId}
          onSelect={(id, label) => {
            setVoiceId(id);
            setVoiceLabel(label);
          }}
          onClose={() => setVoiceModal(false)}
        />
      )}

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
