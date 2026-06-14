"use client";

import { motion } from "framer-motion";
import { X, Check, Circle } from "lucide-react";

const TIPS = [
  "Fale com alta energia — voz expressiva gera avatar expressivo.",
  "Mantenha cabeça e ombros estáveis e centralizados no enquadramento.",
  "Olhe direto para a câmera, com boa iluminação no rosto.",
];

export function RecordingTips({
  onClose,
  onStart,
}: {
  onClose: () => void;
  onStart: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
        className="relative w-full max-w-lg rounded-3xl border border-white/10 bg-panel p-6 shadow-2xl shadow-black/60"
      >
        <button
          onClick={onClose}
          aria-label="Fechar"
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 className="text-lg font-bold text-white">Gravando um ótimo avatar</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Sua voz e seu vídeo guiam os movimentos do avatar. Veja como capturar as melhores
          imagens:
        </p>

        {/* DO / DON'T cards */}
        <div className="mt-4 grid grid-cols-2 gap-3">
          <ExampleCard
            kind="do"
            label="FAÇA"
            gradient="from-emerald-400/40 via-teal-500/20 to-zinc-900/40"
            caption="Energia, postura estável, rosto iluminado."
          />
          <ExampleCard
            kind="dont"
            label="EVITE"
            gradient="from-rose-500/40 via-red-600/20 to-zinc-900/40"
            caption="Imóvel, sem energia, mal enquadrado."
          />
        </div>

        {/* Tips */}
        <ul className="mt-4 space-y-2">
          {TIPS.map((t) => (
            <li key={t} className="flex items-start gap-2.5 text-sm text-zinc-300">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" strokeWidth={3} />
              {t}
            </li>
          ))}
        </ul>

        <div className="mt-6 flex justify-center">
          <button
            onClick={onStart}
            className="flex items-center gap-2 rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
          >
            <Circle className="h-3.5 w-3.5 fill-red-500 text-red-500" />
            Iniciar gravação
          </button>
        </div>
      </motion.div>
    </div>
  );
}

function ExampleCard({
  kind,
  label,
  gradient,
  caption,
}: {
  kind: "do" | "dont";
  label: string;
  gradient: string;
  caption: string;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10">
      <div className={`relative h-28 bg-gradient-to-br ${gradient}`}>
        <span
          className={`absolute left-2 top-2 rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white ${
            kind === "do" ? "bg-emerald-500/80" : "bg-rose-500/80"
          }`}
        >
          {label}
        </span>
      </div>
      <p className="px-3 py-2 text-xs text-zinc-400">{caption}</p>
    </div>
  );
}
