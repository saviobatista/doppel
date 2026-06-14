"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/cn";

const STYLE_PILLS = [
  "Elevado",
  "Amigável",
  "Minimalista",
  "Corporativo",
  "Ousado",
  "Editorial",
  "Retrô",
  "Luxo",
  "Tech",
];

const SUBNAV = [
  "Meus modelos",
  "Recomendados",
  "Em alta",
  "Treinamento",
  "Marketing",
  "Social",
];

const GRADIENTS = [
  "from-violet-500/60 to-fuchsia-700/30",
  "from-sky-500/60 to-cyan-700/30",
  "from-emerald-500/60 to-teal-700/30",
  "from-amber-500/60 to-orange-700/30",
  "from-rose-500/60 to-pink-700/30",
  "from-indigo-500/60 to-blue-700/30",
];

const CARDS = Array.from({ length: 12 }).map((_, i) => ({
  id: i,
  title: ["Lançamento de produto", "Depoimento", "Promoção relâmpago", "Tutorial rápido", "Anúncio UGC", "Notícia do dia"][i % 6],
  ratio: "9:16",
  category: ["Marketing", "Social", "Vendas"][i % 3],
  gradient: GRADIENTS[i % GRADIENTS.length],
}));

export function TemplatesView() {
  const [activeStyles, setActiveStyles] = useState<string[]>([]);
  const [subnav, setSubnav] = useState(SUBNAV[1]);
  const [query, setQuery] = useState("");

  const toggleStyle = (s: string) =>
    setActiveStyles((cur) =>
      cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s],
    );

  return (
    <div className="mx-auto w-full max-w-6xl px-8 pb-16">
      <section className="pt-6">
        <h1 className="text-2xl font-bold text-white">Modelos</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Comece a partir de um modelo e personalize com seu avatar.
        </p>
      </section>

      {/* Search + style pill carousel */}
      <div className="mt-6 flex items-center gap-3">
        <div className="relative shrink-0">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar modelos"
            className="w-64 rounded-full border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-accent/50 focus:outline-none"
          />
        </div>

        <div className="no-scrollbar flex gap-2 overflow-x-auto">
          {STYLE_PILLS.map((s) => {
            const on = activeStyles.includes(s);
            return (
              <button
                key={s}
                onClick={() => toggleStyle(s)}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                  on
                    ? "border-accent/40 bg-accent/15 text-accent"
                    : "border-white/10 bg-white/[0.03] text-zinc-400 hover:border-white/20 hover:text-zinc-200",
                )}
              >
                <span
                  className={cn(
                    "h-3.5 w-6 rounded-full p-0.5 transition-colors",
                    on ? "bg-accent/40" : "bg-white/10",
                  )}
                >
                  <span
                    className={cn(
                      "block h-2.5 w-2.5 rounded-full bg-white transition-transform",
                      on && "translate-x-2.5",
                    )}
                  />
                </span>
                {s}
              </button>
            );
          })}
        </div>
      </div>

      {/* Sub-navigation */}
      <div className="mt-5 flex gap-5 border-b border-white/5">
        {SUBNAV.map((s) => (
          <button
            key={s}
            onClick={() => setSubnav(s)}
            className={cn(
              "relative pb-3 text-sm transition-colors",
              subnav === s ? "font-medium text-white" : "text-zinc-500 hover:text-zinc-300",
            )}
          >
            {s}
            {subnav === s && (
              <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-accent" />
            )}
          </button>
        ))}
      </div>

      {/* Dense template grid */}
      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {CARDS.map((c) => (
          <button
            key={c.id}
            className="group relative aspect-[9/16] overflow-hidden rounded-2xl border border-white/10 text-left"
          >
            <div className={`absolute inset-0 bg-gradient-to-br ${c.gradient}`} />
            <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_0%,rgba(255,255,255,0.16),transparent_60%)] opacity-0 transition-opacity group-hover:opacity-100" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent" />

            <span className="absolute left-2 top-2 rounded-md bg-black/40 px-1.5 py-0.5 text-[10px] font-medium text-white/80 backdrop-blur">
              {c.ratio}
            </span>

            <div className="absolute inset-x-0 bottom-0 p-3">
              <p className="text-sm font-semibold leading-tight text-white drop-shadow">
                {c.title}
              </p>
              <span className="mt-1 inline-block rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-white/90 backdrop-blur">
                {c.category}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
