"use client";

import { useRef, useState } from "react";
import { Check, Loader2, Pause, Play } from "lucide-react";
import type { VoiceCandidate } from "@/lib/api";
import { cn } from "@/lib/cn";

interface VoiceCandidatesProps {
  candidates: VoiceCandidate[];
  onSelect: (c: VoiceCandidate) => void | Promise<void>;
  onBack?: () => void;
  selecting?: boolean;
}

/** A/B preview of the cloned-voice candidates (one per provider/model). */
export function VoiceCandidates({ candidates, onSelect, onBack, selecting }: VoiceCandidatesProps) {
  const [picked, setPicked] = useState<string>(candidates[0] ? keyOf(candidates[0]) : "");
  const [playing, setPlaying] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const toggle = (c: VoiceCandidate) => {
    const k = keyOf(c);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (playing === k || !c.preview_url) {
      setPlaying(null);
      return;
    }
    const audio = new Audio(c.preview_url);
    audio.onended = () => setPlaying(null);
    audio.play().catch(() => setPlaying(null));
    audioRef.current = audio;
    setPlaying(k);
  };

  const chosen = candidates.find((c) => keyOf(c) === picked) ?? candidates[0];

  return (
    <div className="mx-auto w-full max-w-lg">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white">Voz clonada pronta</h2>
        <p className="mt-1.5 text-sm text-zinc-400">
          Ouça as opções abaixo e escolha a que mais soa como você.
        </p>
      </div>

      <div className="mt-6 space-y-3">
        {candidates.map((c) => {
          const k = keyOf(c);
          const active = picked === k;
          return (
            <button
              key={k}
              onClick={() => setPicked(k)}
              className={cn(
                "flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
                active
                  ? "border-accent/70 bg-accent/10"
                  : "border-white/10 bg-white/5 hover:bg-white/10",
              )}
            >
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(c);
                }}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
              >
                {playing === k ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-white">{c.label}</span>
                <span className="block text-xs text-zinc-500">{c.provider}</span>
              </span>
              {active && <Check className="h-5 w-5 shrink-0 text-accent" />}
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex items-center justify-center gap-6">
        {onBack && (
          <button
            onClick={onBack}
            disabled={selecting}
            className="text-sm font-medium text-zinc-300 transition-colors hover:text-white disabled:opacity-50"
          >
            Voltar
          </button>
        )}
        <button
          disabled={!chosen || selecting}
          onClick={() => chosen && onSelect(chosen)}
          className={cn(
            "flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-semibold transition-colors",
            chosen && !selecting
              ? "bg-accent text-obsidian hover:bg-accent-strong"
              : "cursor-not-allowed bg-white/10 text-zinc-500",
          )}
        >
          {selecting && <Loader2 className="h-4 w-4 animate-spin" />}
          {selecting ? "Salvando…" : "Usar esta voz"}
        </button>
      </div>
    </div>
  );
}

function keyOf(c: VoiceCandidate): string {
  return `${c.provider}:${c.model ?? ""}`;
}
