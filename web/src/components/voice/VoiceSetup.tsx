"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Film, Loader2, Mic, Sparkles } from "lucide-react";
import Link from "next/link";
import {
  createVoice,
  selectVoice,
  subscribeVoice,
  type VoiceCandidate,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { VoiceCandidates } from "@/components/voice/VoiceCandidates";
import { VoiceCloneDialog } from "@/components/voice/VoiceCloneDialog";

interface VoiceSetupProps {
  avatarId: string;
  defaultLabel?: string;
  /** The footage carries usable audio (true once avatar prep finished). */
  footageReady?: boolean;
}

type Phase = "choose" | "cloning" | "review" | "done";

export function VoiceSetup({ avatarId, defaultLabel, footageReady = true }: VoiceSetupProps) {
  const [phase, setPhase] = useState<Phase>("choose");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [voiceId, setVoiceId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<VoiceCandidate[]>([]);
  const [selecting, setSelecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const label = (defaultLabel?.trim() ? `Voz de ${defaultLabel.trim()}` : "Minha voz").slice(0, 80);

  const runClone = useCallback(
    async (create: () => Promise<{ voice_id: string; status?: string }>) => {
    setError(null);
    setPhase("cloning");
    try {
      const { voice_id: id, status } = await create();
      setVoiceId(id);
      // Footage reuses the avatar's existing clone — it's ready immediately,
      // no provider A/B and no new ElevenLabs voice.
      if (status === "ready") {
        setPhase("done");
        return;
      }
      abortRef.current?.abort();
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
            setError("Não foi possível clonar a voz. Tente novamente.");
            setPhase("choose");
            ac.abort();
          }
        },
        ac.signal,
      );
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError((e as Error).message);
      setPhase("choose");
    }
  }, []);

  const useFootage = () =>
    runClone(() => createVoice({ source: "footage", avatarId, label }));

  const onGenerate = async (sample: Blob, name: string) => {
    setDialogOpen(false);
    await runClone(() =>
      createVoice({
        source: "recorded",
        avatarId,
        sample,
        sampleName: "voice-sample.webm",
        label: name,
      }),
    );
  };

  const onSelect = async (c: VoiceCandidate) => {
    if (!voiceId) return;
    setSelecting(true);
    try {
      await selectVoice(voiceId, { provider: c.provider, model: c.model });
      setPhase("done");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSelecting(false);
    }
  };

  if (phase === "done") {
    return (
      <div className="mx-auto flex w-full max-w-md flex-col items-center text-center">
        <CheckCircle2 className="h-12 w-12 text-accent" />
        <h2 className="mt-4 text-xl font-bold text-white">Voz salva!</h2>
        <p className="mt-1.5 text-sm text-zinc-400">
          Sua voz foi adicionada às suas vozes e está pronta para gerar vídeos.
        </p>
        <div className="mt-6 flex items-center gap-4">
          <Link
            href="/avatar/vozes"
            className="text-sm font-medium text-zinc-300 transition-colors hover:text-white"
          >
            Ver minhas vozes
          </Link>
          <Link
            href={`/agente?avatar=${avatarId}`}
            className="flex items-center gap-2 rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
          >
            <Sparkles className="h-4 w-4" />
            Criar vídeo
          </Link>
        </div>
      </div>
    );
  }

  if (phase === "cloning") {
    return (
      <div className="mx-auto flex w-full max-w-md flex-col items-center text-center">
        <Loader2 className="h-10 w-10 animate-spin text-accent" />
        <h2 className="mt-4 text-lg font-semibold text-white">Clonando sua voz…</h2>
        <p className="mt-1.5 text-sm text-zinc-400">
          Gerando opções de provedores. Isso leva alguns instantes.
        </p>
      </div>
    );
  }

  if (phase === "review") {
    return (
      <VoiceCandidates
        candidates={candidates}
        onSelect={onSelect}
        onBack={() => setPhase("choose")}
        selecting={selecting}
      />
    );
  }

  return (
    <>
      <div className="mx-auto w-full max-w-2xl">
        <div className="grid gap-4 sm:grid-cols-2">
          <button
            onClick={() => setDialogOpen(true)}
            className="group relative flex flex-col rounded-2xl border border-accent/40 bg-accent/5 p-5 text-left transition-colors hover:bg-accent/10"
          >
            <span className="absolute right-4 top-4 rounded-full bg-accent/20 px-2 py-0.5 text-[11px] font-semibold text-accent">
              Recomendado
            </span>
            <Mic className="h-6 w-6 text-accent" />
            <span className="mt-3 text-base font-semibold text-white">Gravar nova voz</span>
            <span className="mt-1 text-sm text-zinc-400">
              A melhor qualidade: crie um clone de voz dedicado a partir de uma gravação limpa.
            </span>
          </button>

          <button
            onClick={useFootage}
            disabled={!footageReady}
            className={cn(
              "flex flex-col rounded-2xl border border-white/10 bg-white/5 p-5 text-left transition-colors",
              footageReady ? "hover:bg-white/10" : "cursor-not-allowed opacity-50",
            )}
          >
            <Film className="h-6 w-6 text-zinc-300" />
            <span className="mt-3 text-base font-semibold text-white">Usar voz da gravação</span>
            <span className="mt-1 text-sm text-zinc-400">
              Clone a voz diretamente do vídeo que você acabou de gravar.
            </span>
          </button>
        </div>

        {error && <p className="mt-5 text-center text-sm text-red-300">{error}</p>}
      </div>

      {dialogOpen && (
        <VoiceCloneDialog
          defaultName={defaultLabel}
          onClose={() => setDialogOpen(false)}
          onGenerate={onGenerate}
        />
      )}
    </>
  );
}
