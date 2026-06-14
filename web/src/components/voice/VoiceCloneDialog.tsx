"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square, Trash2, Upload, X } from "lucide-react";
import { cn } from "@/lib/cn";

interface VoiceCloneDialogProps {
  defaultName?: string;
  onClose: () => void;
  /** Hand the captured sample to the parent, which kicks off the clone job. */
  onGenerate: (sample: Blob, name: string) => void | Promise<void>;
}

type Tab = "record" | "upload";
type Step = "capture" | "review";

const TARGET_SECONDS = 30;

const SCRIPT =
  "Grave com energia e naturalidade por pelo menos 30 segundos, em um ambiente silencioso. " +
  "Leia este texto em voz alta, como se estivesse conversando com um amigo. " +
  "Quanto mais clara e expressiva for a sua fala, melhor ficará a sua voz clonada — " +
  "pronta para narrar qualquer vídeo no seu lugar, a qualquer hora.";

export function VoiceCloneDialog({ defaultName, onClose, onGenerate }: VoiceCloneDialogProps) {
  const [tab, setTab] = useState<Tab>("record");
  const [step, setStep] = useState<Step>("capture");
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [sample, setSample] = useState<Blob | null>(null);
  const [sampleUrl, setSampleUrl] = useState<string | null>(null);
  const [name, setName] = useState(defaultName ?? "");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cleanup = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };
  useEffect(() => () => cleanup(), []);
  useEffect(() => {
    return () => {
      if (sampleUrl) URL.revokeObjectURL(sampleUrl);
    };
  }, [sampleUrl]);

  const accept = (blob: Blob) => {
    setSample(blob);
    setSampleUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(blob);
    });
    setStep("review");
  };

  const startRecording = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        cleanup();
        accept(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
      };
      recorderRef.current = rec;
      rec.start();
      setRecording(true);
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } catch {
      setError("Não foi possível acessar o microfone. Verifique as permissões.");
    }
  };

  const stopRecording = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setRecording(false);
    recorderRef.current?.stop();
  };

  const onUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setName((n) => n || file.name.replace(/\.[^.]+$/, ""));
      accept(file);
    }
  };

  const discard = () => {
    setSample(null);
    setStep("capture");
    setElapsed(0);
  };

  const generate = async () => {
    if (!sample || generating) return;
    setGenerating(true);
    setError(null);
    try {
      await onGenerate(sample, name.trim() || "Minha voz");
    } catch (err) {
      setError((err as Error).message);
      setGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-xl rounded-2xl border border-white/10 bg-panel p-6 shadow-2xl">
        <button
          onClick={onClose}
          aria-label="Fechar"
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
        >
          <X className="h-4 w-4" />
        </button>

        {step === "capture" ? (
          <>
            <h2 className="text-xl font-bold text-white">Criar clone de voz</h2>
            <p className="mt-1.5 text-sm text-zinc-400">
              Fale com energia e grave por pelo menos 30 segundos com um bom microfone.
            </p>

            <div className="mt-5 grid grid-cols-2 rounded-full border border-white/10 bg-white/5 p-1">
              <TabButton active={tab === "record"} onClick={() => setTab("record")} icon={Mic}>
                Gravar áudio
              </TabButton>
              <TabButton active={tab === "upload"} onClick={() => setTab("upload")} icon={Upload}>
                Enviar áudio
              </TabButton>
            </div>

            {tab === "record" ? (
              <>
                <div className="mt-5 max-h-44 overflow-y-auto rounded-xl border border-white/10 bg-white/5 p-4 text-sm leading-relaxed text-zinc-300">
                  {SCRIPT}
                </div>
                <div className="mt-6 flex flex-col items-center gap-3">
                  <button
                    onClick={recording ? stopRecording : startRecording}
                    className={cn(
                      "flex h-16 w-16 items-center justify-center rounded-full transition-colors",
                      recording
                        ? "bg-red-500/20 text-red-300 hover:bg-red-500/30"
                        : "bg-accent text-obsidian hover:bg-accent-strong",
                    )}
                  >
                    {recording ? <Square className="h-6 w-6" /> : <Mic className="h-7 w-7" />}
                  </button>
                  <span className="font-mono text-sm text-zinc-400">
                    {fmt(elapsed)} / {fmt(TARGET_SECONDS)}
                  </span>
                </div>
              </>
            ) : (
              <label className="mt-6 flex cursor-pointer flex-col items-center gap-3 rounded-xl border border-dashed border-white/15 bg-white/5 px-6 py-10 text-center transition-colors hover:bg-white/10">
                <Upload className="h-7 w-7 text-zinc-400" />
                <span className="text-sm text-zinc-300">
                  Clique para enviar um arquivo de áudio (MP3, WAV, M4A…)
                </span>
                <input type="file" accept="audio/*" className="hidden" onChange={onUpload} />
              </label>
            )}
          </>
        ) : (
          <>
            <h2 className="text-xl font-bold text-white">Revisar gravação</h2>
            <p className="mt-1.5 text-sm text-zinc-400">
              Ouça, dê um nome e gere o seu clone de voz.
            </p>

            <label className="mt-5 block text-sm font-medium text-zinc-200">Nome da voz</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex.: Minha voz"
              className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder:text-zinc-500 focus:border-accent/60 focus:outline-none focus:ring-1 focus:ring-accent/40"
            />

            <div className="mt-5 flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
              {sampleUrl && <audio src={sampleUrl} controls className="h-9 min-w-0 flex-1" />}
              <button
                onClick={discard}
                aria-label="Descartar"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-8 flex items-center justify-end gap-4">
              <button
                onClick={discard}
                disabled={generating}
                className="text-sm font-medium text-zinc-300 transition-colors hover:text-white disabled:opacity-50"
              >
                Voltar
              </button>
              <button
                onClick={generate}
                disabled={generating}
                className="flex items-center gap-2 rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong disabled:opacity-60"
              >
                {generating && <Loader2 className="h-4 w-4 animate-spin" />}
                {generating ? "Gerando…" : "Gerar voz"}
              </button>
            </div>
          </>
        )}

        {error && <p className="mt-4 text-center text-sm text-red-300">{error}</p>}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Mic;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center justify-center gap-2 rounded-full py-2 text-sm font-medium transition-colors",
        active ? "bg-white/10 text-white" : "text-zinc-400 hover:text-zinc-200",
      )}
    >
      <Icon className="h-4 w-4" />
      {children}
    </button>
  );
}

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}
