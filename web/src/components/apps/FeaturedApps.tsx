"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

const FEATURED = [
  {
    title: "Gerador de Vídeo com IA",
    desc: "Do briefing ao anúncio vertical pronto em minutos.",
    gradient: "from-violet-500/60 via-fuchsia-600/30 to-zinc-900/30",
  },
  {
    title: "One Shot Edit",
    desc: "Edite vídeos inteiros com um único comando.",
    gradient: "from-sky-400/60 via-cyan-600/30 to-zinc-900/30",
  },
  {
    title: "Clipes automáticos",
    desc: "Recorte os melhores momentos automaticamente.",
    gradient: "from-amber-400/60 via-rose-600/30 to-zinc-900/30",
  },
];

export function FeaturedApps() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {FEATURED.map((f) => (
        <motion.button
          key={f.title}
          whileHover={{ y: -3 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          className="group relative h-40 overflow-hidden rounded-3xl border border-white/10 text-left"
        >
          <div className={`absolute inset-0 bg-gradient-to-br ${f.gradient}`} />
          <div className="absolute inset-0 bg-[radial-gradient(120%_120%_at_85%_10%,rgba(255,255,255,0.16),transparent_55%)]" />
          <div className="absolute inset-0 flex flex-col justify-end gap-1 p-5">
            <h3 className="text-lg font-bold text-white drop-shadow">{f.title}</h3>
            <p className="text-sm text-white/75">{f.desc}</p>
            <span className="mt-1 flex items-center gap-1 text-sm font-medium text-white">
              Abrir
              <ArrowRight className="h-4 w-4 -translate-x-1 opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
            </span>
          </div>
        </motion.button>
      ))}
    </div>
  );
}
