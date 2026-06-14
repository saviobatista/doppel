"use client";

import { useMemo, useState } from "react";
import {
  Search,
  Wand2,
  Languages,
  Image as ImageIcon,
  Scissors,
  Mic,
  FileVideo,
  Presentation,
  Music,
  Subtitles,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface Tool {
  title: string;
  desc: string;
  icon: LucideIcon;
  tint: string;
  category: "criar" | "editar" | "traduzir";
  badge?: string;
}

const TOOLS: Tool[] = [
  { title: "Gerador de Vídeo", desc: "Texto ou briefing em vídeo completo.", icon: Wand2, tint: "from-violet-500 to-fuchsia-600", category: "criar", badge: "NOVO" },
  { title: "Foto para Vídeo", desc: "Anime qualquer imagem estática.", icon: ImageIcon, tint: "from-pink-500 to-rose-600", category: "criar" },
  { title: "Apresentação para Vídeo", desc: "PPT ou PDF viram narração visual.", icon: Presentation, tint: "from-amber-400 to-orange-600", category: "criar" },
  { title: "Tradutor de Vídeo", desc: "Dublagem e legendas em 30+ idiomas.", icon: Languages, tint: "from-sky-400 to-cyan-600", category: "traduzir", badge: "NOVO" },
  { title: "Legendas Automáticas", desc: "Legendas sincronizadas em segundos.", icon: Subtitles, tint: "from-teal-400 to-emerald-600", category: "editar" },
  { title: "Clipes Automáticos", desc: "Recorte os melhores momentos.", icon: Scissors, tint: "from-emerald-400 to-green-600", category: "editar" },
  { title: "Clonagem de Voz", desc: "Sua voz, em qualquer roteiro.", icon: Mic, tint: "from-indigo-400 to-blue-600", category: "criar" },
  { title: "Trilha com IA", desc: "Música original sob medida.", icon: Music, tint: "from-rose-400 to-pink-600", category: "criar" },
  { title: "Conversor de Formato", desc: "Reenquadre para qualquer plataforma.", icon: FileVideo, tint: "from-cyan-400 to-sky-600", category: "editar" },
];

const FILTERS = [
  { id: "todos", label: "Todos os apps" },
  { id: "criar", label: "Criar" },
  { id: "editar", label: "Editar" },
  { id: "traduzir", label: "Traduzir" },
] as const;

export function AppCatalog() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("todos");
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    return TOOLS.filter((t) => {
      const matchFilter = filter === "todos" || t.category === filter;
      const matchQuery =
        !query.trim() ||
        (t.title + " " + t.desc).toLowerCase().includes(query.toLowerCase());
      return matchFilter && matchQuery;
    });
  }, [filter, query]);

  return (
    <div>
      {/* Sticky filter + search row */}
      <div className="sticky top-0 z-10 -mx-8 mb-5 bg-obsidian/80 px-8 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={cn(
                  "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
                  filter === f.id
                    ? "bg-white/10 text-white ring-1 ring-white/15"
                    : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar apps"
              className="w-56 rounded-full border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-accent/50 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Tool grid */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {visible.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.title}
              className="group flex items-start gap-3 rounded-2xl border border-white/5 bg-panel/40 p-4 text-left transition-colors hover:border-white/15 hover:bg-panel-2/60"
            >
              <span
                className={cn(
                  "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-white shadow-lg",
                  t.tint,
                )}
              >
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="truncate font-semibold text-zinc-100">{t.title}</h3>
                  {t.badge && (
                    <span className="rounded-md bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-accent">
                      {t.badge}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-sm text-zinc-400">{t.desc}</p>
              </div>
            </button>
          );
        })}
      </div>

      {visible.length === 0 && (
        <p className="py-16 text-center text-sm text-zinc-500">
          Nenhum app encontrado para “{query}”.
        </p>
      )}
    </div>
  );
}
