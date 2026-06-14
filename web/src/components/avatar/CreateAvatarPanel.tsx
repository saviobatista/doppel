"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

interface Option {
  title: string;
  desc: string;
  href: string;
  badge?: string;
  gradient: string;
}

const OPTIONS: Option[] = [
  {
    title: "Clonar uma pessoa real",
    desc: "Use gravações reais para criar um avatar que se parece, se movimenta e soa como você.",
    href: "/avatar/clonar",
    badge: "Avatar V",
    gradient: "from-amber-300/40 via-orange-500/20 to-zinc-900/30",
  },
  {
    title: "Criar um personagem virtual",
    desc: "Comece com uma imagem e dê vida a ela com movimentação e voz únicas.",
    href: "/avatar/studio",
    gradient: "from-emerald-300/40 via-teal-500/20 to-zinc-900/30",
  },
];

export function CreateAvatarPanel() {
  return (
    <div className="mx-auto max-w-3xl px-8 py-12 text-center">
      <h2 className="text-2xl font-bold text-white">Crie seu primeiro Avatar</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm text-zinc-400">
        Crie uma identidade que mantém aparência, movimentos e voz consistentes em qualquer
        roupa e ambiente.{" "}
        <Link href="/avatar/studio" className="text-accent hover:underline">
          Ver o guia
        </Link>
      </p>

      <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
        {OPTIONS.map((o) => (
          <motion.div
            key={o.title}
            whileHover={{ y: -3 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
          >
            <Link
              href={o.href}
              className="group block overflow-hidden rounded-3xl border border-white/10 bg-panel/40 text-left transition-colors hover:border-accent/40"
            >
              {/* Diagonal-cut visual frame */}
              <div className="relative h-40 overflow-hidden">
                <div className={`absolute inset-0 bg-gradient-to-br ${o.gradient}`} />
                <div
                  className="absolute inset-0 opacity-60"
                  style={{
                    background:
                      "repeating-linear-gradient(135deg, rgba(255,255,255,0.06) 0 2px, transparent 2px 22px)",
                  }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-panel/80 to-transparent" />
              </div>

              <div className="p-5">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-white">{o.title}</h3>
                  {o.badge && (
                    <span className="rounded-md bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium text-accent">
                      {o.badge}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-sm text-zinc-400">{o.desc}</p>
              </div>
            </Link>
          </motion.div>
        ))}
      </div>

      <Link
        href="/avatar/publicos"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-zinc-300 transition-colors hover:text-white"
      >
        Experimente um Avatar público
        <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}
