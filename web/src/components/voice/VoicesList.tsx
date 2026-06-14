"use client";

import { useEffect, useRef, useState } from "react";
import { AudioLines, Loader2, Mic, Plus } from "lucide-react";
import {
  createVoice,
  listVoices,
  selectVoice,
  subscribeVoice,
  type VoiceCandidate,
  type VoiceSummary,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { VoiceCandidates } from "@/components/voice/VoiceCandidates";
import { VoiceCloneDialog } from "@/components/voice/VoiceCloneDialog";

type CreatePhase = "dialog" | "cloning" | "review";

export function VoicesList() {
  const [voices, setVoices] = useState<VoiceSummary[] | null>(null);
  const [phase, setPhase] = useState<CreatePhase | null>(null);
  const [voiceId, setVoiceId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<VoiceCandidate[]>([]);
  const [selecting, setSelecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = () => listVoices().then(setVoices).catch(() => setVoices([]));
  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, []);

  const onGenerate = async (sample: Blob, name: string) => {
    setError(null);
    setPhase("cloning");
    try {
      const { voice_id: id } = await createVoice({
        source: "recorded",
        sample,
        sampleName: "voice-sample.webm",
        label: name,
      });
      setVoiceId(id);
      const ac = new AbortController();
      abortRef.current = ac;
      await subscribeVoice(
        id,
        (event, data) => {
          if (event === "ready") {
            setCandidates((data.candidates as VoiceCandidate[]) ?? []);
            setPhase("review");
            ac.abort();
          } else if (event === "failed") {
            setError("Não foi possível clonar a voz.");
            setPhase(null);
            ac.abort();
          }
        },
        ac.signal,
      );
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError((e as Error).message);
      setPhase(null);
    }
  };

  const onSelect = async (c: VoiceCandidate) => {
    if (!voiceId) return;
    setSelecting(true);
    try {
      await selectVoice(voiceId, { provider: c.provider, model: c.model });
      setPhase(null);
      setVoiceId(null);
      setCandidates([]);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSelecting(false);
    }
  };

  const closeCreate = () => {
    abortRef.current?.abort();
    setPhase(null);
    setVoiceId(null);
    setCandidates([]);
  };

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Minhas vozes</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Clone e gerencie vozes reutilizáveis para seus avatares e vídeos.
          </p>
        </div>
        <button
          onClick={() => setPhase("dialog")}
          className="flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
        >
          <Plus className="h-4 w-4" />
          Clonar sua voz
        </button>
      </div>

      <div className="mt-8">
        {voices === null ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
          </div>
        ) : voices.length === 0 ? (
          <div className="flex flex-col items-center rounded-2xl border border-dashed border-white/10 px-8 py-16 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-zinc-400">
              <AudioLines className="h-6 w-6" />
            </span>
            <h2 className="mt-4 text-base font-semibold text-white">Nenhuma voz ainda</h2>
            <p className="mt-1 max-w-xs text-sm text-zinc-500">
              Clone sua primeira voz para narrar seus vídeos automaticamente.
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {voices.map((v) => (
              <li
                key={v.voice_id}
                className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-zinc-300">
                  <Mic className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-white">{v.label}</span>
                  <span className="block text-xs text-zinc-500">
                    {labelFor(v)}
                  </span>
                </span>
                <StatusBadge status={v.status} />
              </li>
            ))}
          </ul>
        )}
        {error && !phase && <p className="mt-4 text-sm text-red-300">{error}</p>}
      </div>

      {phase === "dialog" && (
        <VoiceCloneDialog onClose={closeCreate} onGenerate={onGenerate} />
      )}

      {(phase === "cloning" || phase === "review") && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-2xl border border-white/10 bg-panel p-6 shadow-2xl">
            {phase === "cloning" ? (
              <div className="flex flex-col items-center py-8 text-center">
                <Loader2 className="h-10 w-10 animate-spin text-accent" />
                <h2 className="mt-4 text-lg font-semibold text-white">Clonando sua voz…</h2>
                <p className="mt-1.5 text-sm text-zinc-400">
                  Gerando opções de provedores.
                </p>
              </div>
            ) : (
              <VoiceCandidates
                candidates={candidates}
                onSelect={onSelect}
                onBack={closeCreate}
                selecting={selecting}
              />
            )}
            {error && <p className="mt-4 text-center text-sm text-red-300">{error}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function labelFor(v: VoiceSummary): string {
  const src =
    v.source === "footage" ? "Da gravação" : v.source === "uploaded" ? "Enviada" : "Gravada";
  const provider = v.provider ? ` · ${v.provider}` : "";
  return `${src}${provider}`;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    ready: { label: "Pronta", cls: "bg-emerald-500/15 text-emerald-300" },
    cloning: { label: "Clonando", cls: "bg-amber-500/15 text-amber-300" },
    failed: { label: "Falhou", cls: "bg-red-500/15 text-red-300" },
  };
  const s = map[status] ?? { label: status, cls: "bg-white/10 text-zinc-300" };
  return (
    <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-xs font-medium", s.cls)}>
      {s.label}
    </span>
  );
}
