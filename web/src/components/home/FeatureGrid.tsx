"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

interface Feature {
  title: string;
  cta: string;
  href: string;
  gradient: string;
}

const FEATURES: Feature[] = [
  {
    title: "Criar um Avatar",
    cta: "Ir para Avatares",
    href: "/avatar",
    gradient: "from-lime-400/80 via-emerald-500/40 to-emerald-900/20",
  },
  {
    title: "One Shot Edit",
    cta: "Criar agora",
    href: "/apps",
    gradient: "from-sky-400/70 via-cyan-600/30 to-slate-900/20",
  },
  {
    title: "Começar do zero",
    cta: "Ir para o AI Studio",
    href: "/avatar/studio",
    gradient: "from-amber-300/70 via-orange-600/30 to-stone-900/20",
  },
  {
    title: "Foto para Vídeo",
    cta: "Experimente agora",
    href: "/apps",
    gradient: "from-pink-500/80 via-fuchsia-600/40 to-purple-900/20",
  },
  {
    title: "Traduzir qualquer vídeo",
    cta: "Traduzir agora",
    href: "/apps",
    gradient: "from-teal-400/70 via-cyan-700/30 to-slate-900/20",
  },
  {
    title: "PPT ou PDF para Vídeo",
    cta: "Experimente agora",
    href: "/apps",
    gradient: "from-rose-400/70 via-pink-700/30 to-zinc-900/20",
  },
];

export function FeatureGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {FEATURES.map((f) => (
        <motion.div
          key={f.title}
          whileHover={{ y: -3 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        >
          <Link
            href={f.href}
            className="group relative block h-44 overflow-hidden rounded-3xl border border-white/10"
          >
            {/* Gradient backdrop (placeholder for rich imagery) */}
            <div className={`absolute inset-0 bg-gradient-to-br ${f.gradient}`} />
            <div className="absolute inset-0 bg-[radial-gradient(120%_120%_at_80%_0%,rgba(255,255,255,0.18),transparent_55%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />

            {/* Title + CTA */}
            <div className="absolute inset-x-0 top-0 p-5">
              <h3 className="max-w-[60%] text-xl font-bold leading-tight text-white drop-shadow">
                {f.title}
              </h3>
            </div>
            <div className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 p-5 text-sm font-medium text-white/90">
              {f.cta}
              <ArrowRight className="h-4 w-4 -translate-x-1 opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
            </div>
          </Link>
        </motion.div>
      ))}
    </div>
  );
}
