"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Pause, Play, UserRound, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { getVoicePreview, type VoiceSummary } from "@/lib/api";

interface Props {
  voices: VoiceSummary[];
  /** Empty string means "use the avatar's own voice". */
  value: string;
  onSelect: (voiceId: string, label: string) => void;
  onClose: () => void;
}

const SOURCE_LABEL: Record<string, string> = {
  footage: "Do avatar",
  recorded: "Gravada",
  uploaded: "Enviada",
};

function meta(v: VoiceSummary): string {
  const parts = [v.provider ?? "Voz clonada", SOURCE_LABEL[v.source] ?? v.source];
  return parts.filter(Boolean).join(" · ");
}

export function VoicePickerModal({ voices, value, onSelect, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [playing, setPlaying] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cacheRef = useRef<Record<string, string>>({});

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      audioRef.current?.pause();
    };
  }, [onClose]);

  const ready = voices.filter((v) => v.status === "ready");
  const filtered = query
    ? ready.filter((v) => v.label.toLowerCase().includes(query.toLowerCase()))
    : ready;

  const togglePlay = async (voiceId: string) => {
    if (playing === voiceId) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }
    audioRef.current?.pause();
    setPlaying(null);
    let url = cacheRef.current[voiceId];
    if (url === undefined) {
      setLoadingPreview(voiceId);
      try {
        url = await getVoicePreview(voiceId);
        cacheRef.current[voiceId] = url;
      } catch {
        url = "";
      } finally {
        setLoadingPreview(null);
      }
    }
    if (!url) return;
    if (!audioRef.current) audioRef.current = new Audio();
    audioRef.current.src = url;
    audioRef.current.onended = () => setPlaying(null);
    try {
      await audioRef.current.play();
      setPlaying(voiceId);
    } catch {
      setPlaying(null);
    }
  };

  const select = (voiceId: string, label: string) => {
    audioRef.current?.pause();
    onSelect(voiceId, label);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="relative flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-white/10 bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/5 px-6 py-4">
          <h2 className="text-lg font-bold text-white">Escolher voz</h2>
          <button
            onClick={onClose}
            aria-label="Fechar"
            className="flex h-8 w-8 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 pt-4">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar vozes…"
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder:text-zinc-500 focus:border-accent/60 focus:outline-none focus:ring-1 focus:ring-accent/40"
          />
        </div>

        <div className="flex flex-col gap-1 overflow-y-auto px-4 py-3">
          <Row
            selected={value === ""}
            onSelect={() => select("", "Voz do avatar")}
            title="Voz do avatar"
            subtitle="Usa a voz original do avatar"
          />
          {filtered.map((v) => (
            <Row
              key={v.voice_id}
              selected={value === v.voice_id}
              onSelect={() => select(v.voice_id, v.label)}
              title={v.label}
              subtitle={meta(v)}
              playing={playing === v.voice_id}
              loading={loadingPreview === v.voice_id}
              onPlay={() => togglePlay(v.voice_id)}
            />
          ))}
          {filtered.length === 0 && (
            <p className="px-2 py-6 text-center text-sm text-zinc-500">
              Nenhuma voz encontrada.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({
  selected,
  onSelect,
  onPlay,
  title,
  subtitle,
  playing,
  loading,
}: {
  selected: boolean;
  onSelect: () => void;
  onPlay?: () => void;
  title: string;
  subtitle: string;
  playing?: boolean;
  loading?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors",
        selected ? "border-accent/50 bg-accent/10" : "border-transparent hover:bg-white/5",
      )}
    >
      {onPlay ? (
        <button
          onClick={onPlay}
          aria-label={playing ? "Pausar" : "Reproduzir"}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-zinc-100 transition-colors hover:bg-white/20"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : playing ? (
            <Pause className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4 translate-x-px" />
          )}
        </button>
      ) : (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/5 text-zinc-400">
          <UserRound className="h-4 w-4" />
        </span>
      )}
      <button onClick={onSelect} className="min-w-0 flex-1 text-left">
        <p className="truncate text-sm font-semibold text-white">{title}</p>
        <p className="truncate text-xs text-zinc-500">{subtitle}</p>
      </button>
      {selected && <Check className="h-4 w-4 shrink-0 text-accent" />}
    </div>
  );
}
