"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Lock, Sparkles } from "lucide-react";
import { SCENARIOS } from "@/lib/scenarios";
import { cn } from "@/lib/cn";

export function CategoryGrid() {
  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-bold text-white">Criar vídeo com cenário</h1>
        <p className="mt-2 text-zinc-400">
          Escolha uma categoria. Respondemos algumas perguntas e montamos o cenário ideal para o seu
          avatar — pronto para gravar e viralizar.
        </p>
      </div>

      {/* Featured: Video Agent */}
      <Link href="/agente" className="mt-8 block">
        <motion.div
          whileHover={{ y: -3 }}
          className="group relative flex items-center gap-5 overflow-hidden rounded-3xl border border-accent/30 bg-panel p-6"
        >
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_140%_at_15%_0%,rgba(56,189,248,0.22),rgba(168,85,247,0.12),transparent_70%)]" />
          <span className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-accent/15 text-accent ring-1 ring-accent/30">
            <Sparkles className="h-7 w-7" />
          </span>
          <div className="relative min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white">Agente de Vídeo</h2>
              <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent ring-1 ring-accent/30">
                Novo
              </span>
            </div>
            <p className="mt-1 text-sm text-zinc-400">
              Descreva uma ideia. O agente pesquisa na web, escreve o roteiro, dirige as cenas e
              monta o plano completo — pronto para gerar.
            </p>
          </div>
          <span className="relative hidden items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-obsidian transition-colors group-hover:bg-accent-strong sm:flex">
            Começar
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </span>
        </motion.div>
      </Link>

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SCENARIOS.map((cat, i) => {
          const Icon = cat.icon;
          const card = (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              whileHover={cat.available ? { y: -4 } : undefined}
              className={cn(
                "group relative flex h-full flex-col overflow-hidden rounded-3xl border border-white/10 bg-panel p-5",
                cat.available ? "cursor-pointer" : "opacity-60",
              )}
            >
              <div
                className={cn(
                  "pointer-events-none absolute inset-0 bg-gradient-to-br opacity-60",
                  cat.gradient,
                )}
              />
              <div className="relative flex h-full flex-col">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-black/30 backdrop-blur">
                  <Icon className="h-5 w-5 text-white" />
                </div>
                <h2 className="mt-4 text-lg font-bold text-white">{cat.title}</h2>
                <p className="text-sm font-medium text-zinc-300">{cat.tagline}</p>
                <p className="mt-2 text-sm text-zinc-400">{cat.description}</p>

                <div className="mt-auto pt-5">
                  {cat.available ? (
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-white">
                      Começar
                      <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500">
                      <Lock className="h-3.5 w-3.5" />
                      Em breve
                    </span>
                  )}
                </div>
              </div>
            </motion.div>
          );

          return cat.available ? (
            <Link key={cat.id} href={`/criar/${cat.id}`}>
              {card}
            </Link>
          ) : (
            <div key={cat.id}>{card}</div>
          );
        })}
      </div>
    </div>
  );
}
