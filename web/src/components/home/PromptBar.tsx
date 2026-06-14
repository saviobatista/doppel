"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Plus,
  ArrowLeftRight,
  ChevronDown,
  ArrowUp,
  Loader2,
  UserRound,
  AudioLines,
  Palette,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { createPlan, listAvatars } from "@/lib/api";

export function PromptBar() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [avatarId, setAvatarId] = useState<string | null>(null);
  const [avatarLabel, setAvatarLabel] = useState("Automático");

  useEffect(() => {
    listAvatars()
      .then((list) => {
        const ready = list.find((a) => a.status === "ready");
        if (ready) {
          setAvatarId(ready.avatar_id);
          setAvatarLabel("Bruno Valerio");
        }
      })
      .catch(() => {});
  }, []);

  const capsules = [
    { id: "avatar", label: "Avatar", value: avatarLabel, icon: UserRound },
    { id: "voice", label: "Voz", value: avatarLabel, icon: AudioLines },
    { id: "style", label: "Estilo/Marca", value: "Automático", icon: Palette },
  ];

  async function submit() {
    if (!value.trim() || submitting) return;
    setSubmitting(true);
    try {
      const planId = await createPlan({
        prompt: value.trim(),
        avatar_id: avatarId,
        avatar_label: avatarLabel,
        voice_label: avatarLabel,
        duration_seconds: 40,
        orientation: "portrait",
        language: "pt-BR",
      });
      router.push(`/agente/${planId}`);
    } catch {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative w-full max-w-2xl">
      {/* Aura glow */}
      <div className="pointer-events-none absolute -inset-x-10 -top-6 bottom-0 -z-10 rounded-[2.5rem] bg-[radial-gradient(60%_120%_at_50%_0%,rgba(56,189,248,0.18),transparent_70%)] blur-2xl" />

      <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-3 shadow-2xl shadow-black/40 backdrop-blur-xl">
        {/* Selection capsules */}
        <div className="flex flex-wrap gap-2">
          {capsules.map((c) => {
            const Icon = c.icon;
            return (
              <button
                key={c.id}
                className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 py-1.5 pl-2 pr-3 text-xs text-zinc-300 transition-colors hover:border-white/20 hover:bg-white/10"
              >
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/10">
                  <Icon className="h-3 w-3" />
                </span>
                <span className="font-medium text-zinc-100">{c.value}</span>
                <span className="text-zinc-500">{c.label}</span>
              </button>
            );
          })}
        </div>

        {/* Input */}
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          placeholder="Peça um vídeo, um avatar ou algo entre os dois — eu começo para você."
          className="mt-3 w-full resize-none bg-transparent px-2 text-[15px] text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
        />

        {/* Actions row */}
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <IconBtn label="Anexar">
              <Plus className="h-[18px] w-[18px]" />
            </IconBtn>
            <IconBtn label="Alternar">
              <ArrowLeftRight className="h-[18px] w-[18px]" />
            </IconBtn>
          </div>

          <div className="flex items-center gap-2">
            <button className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-200 transition-colors hover:bg-white/10">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              Piloto automático
              <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />
            </button>
            <button
              onClick={submit}
              disabled={!value.trim() || submitting}
              className={cn(
                "flex h-9 items-center gap-1.5 rounded-full px-4 text-sm font-semibold transition-all",
                value.trim() && !submitting
                  ? "bg-accent text-obsidian hover:bg-accent-strong"
                  : "cursor-not-allowed bg-white/10 text-zinc-500",
              )}
            >
              {submitting ? "Criando…" : "Enviar"}
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Quick chips */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        {["Usar Avatar", "Usar estilo/marca", "Carregar documentos", "Roteiro para vídeo"].map(
          (chip) => (
            <motion.button
              key={chip}
              whileHover={{ y: -1 }}
              className="rounded-full border border-white/10 bg-white/[0.03] px-3.5 py-1.5 text-xs text-zinc-400 transition-colors hover:border-white/20 hover:text-zinc-200"
            >
              {chip}
            </motion.button>
          ),
        )}
      </div>
    </div>
  );
}

function IconBtn({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <button
      title={label}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-zinc-300 transition-colors hover:bg-white/10"
    >
      {children}
    </button>
  );
}
