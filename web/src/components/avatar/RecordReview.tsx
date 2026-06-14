"use client";

import { useState } from "react";
import { Loader2, ShieldCheck, Trash2, X } from "lucide-react";
import { cn } from "@/lib/cn";

interface RecordReviewProps {
  url: string | null;
  aspect: "landscape" | "portrait";
  onRetake: () => void;
  onClose: () => void;
  onCreate: (name: string) => void | Promise<void>;
}

export function RecordReview({ url, aspect, onRetake, onClose, onCreate }: RecordReviewProps) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isPortrait = aspect === "portrait";

  const submit = async () => {
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      await onCreate(name.trim());
    } catch (e) {
      setError((e as Error).message);
      setCreating(false);
    }
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      {/* Header: close → avatar home */}
      <header className="flex h-14 shrink-0 items-center justify-end px-6">
        <button
          onClick={onClose}
          aria-label="Fechar"
          className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
        >
          <X className="h-5 w-5" />
        </button>
      </header>

      <main className="flex-1 overflow-y-auto px-6 pb-12">
        <div className="mx-auto w-full max-w-xl">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-white">Último passo!</h1>
            <p className="mt-2 text-sm text-zinc-400">
              Revise sua gravação e envie quando estiver pronto para criar seu avatar.
            </p>
          </div>

          {/* Video card */}
          <div
            className={cn(
              "relative mx-auto mt-6 overflow-hidden rounded-2xl border border-white/10 bg-black",
              isPortrait ? "aspect-[9/16] max-h-[60vh] w-auto" : "aspect-video w-full",
            )}
          >
            {url && (
              <video src={url} controls loop className="h-full w-full object-contain" />
            )}

            <span className="pointer-events-none absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur">
              <ShieldCheck className="h-3.5 w-3.5 text-accent" />
              Identidade protegida
            </span>

            <button
              onClick={onRetake}
              aria-label="Descartar gravação"
              className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur transition-colors hover:bg-black/80"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>

          {/* Name field */}
          <div className="mt-6">
            <label htmlFor="avatar-name" className="block text-sm font-medium text-zinc-200">
              Nomeie seu avatar
            </label>
            <input
              id="avatar-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex.: Bruno Valério"
              className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder:text-zinc-500 focus:border-accent/60 focus:outline-none focus:ring-1 focus:ring-accent/40"
            />
          </div>

          {error && (
            <p className="mt-4 text-center text-sm text-red-300">{error}</p>
          )}

          {/* Actions */}
          <div className="mt-8 flex items-center justify-center gap-6">
            <button
              onClick={onRetake}
              disabled={creating}
              className="text-sm font-medium text-zinc-300 transition-colors hover:text-white disabled:opacity-50"
            >
              Gravar novamente
            </button>
            <button
              disabled={!name.trim() || creating}
              onClick={submit}
              className={cn(
                "flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-semibold transition-colors",
                name.trim() && !creating
                  ? "bg-accent text-obsidian hover:bg-accent-strong"
                  : "cursor-not-allowed bg-white/10 text-zinc-500",
              )}
            >
              {creating && <Loader2 className="h-4 w-4 animate-spin" />}
              {creating ? "Enviando…" : "Criar Avatar"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
