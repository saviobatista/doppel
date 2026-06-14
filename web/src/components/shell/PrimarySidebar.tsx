"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Code2, Circle } from "lucide-react";
import { PRIMARY_NAV, PROJECTS_NAV, type PrimaryNavItem } from "@/lib/nav";
import { cn } from "@/lib/cn";

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

function RailItem({ item, active }: { item: PrimaryNavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className="group relative flex flex-col items-center gap-1.5 py-1"
    >
      <span
        className={cn(
          "relative flex h-10 w-10 items-center justify-center rounded-xl transition-colors",
          active
            ? "bg-accent/15 text-accent"
            : "text-zinc-400 hover:bg-white/5 hover:text-zinc-100",
        )}
      >
        {active && (
          <motion.span
            layoutId="rail-active"
            className="absolute inset-0 rounded-xl ring-1 ring-accent/40"
            transition={{ type: "spring", stiffness: 500, damping: 40 }}
          />
        )}
        <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
      </span>
      <span
        className={cn(
          "text-[10px] font-medium leading-none transition-colors",
          active ? "text-zinc-100" : "text-zinc-500 group-hover:text-zinc-300",
        )}
      >
        {item.label}
      </span>
    </Link>
  );
}

export function PrimarySidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-dvh w-[68px] shrink-0 flex-col items-center border-r border-white/5 bg-panel/60 py-3">
      {/* Brand mark */}
      <Link
        href="/"
        className="mb-4 flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-neon-purple text-sm font-black text-obsidian shadow-lg shadow-accent/20"
      >
        d
      </Link>

      {/* Main nav */}
      <nav className="flex flex-col gap-1">
        {PRIMARY_NAV.map((item) => (
          <RailItem key={item.href} item={item} active={isActive(pathname, item.href)} />
        ))}
      </nav>

      {/* Divider */}
      <div className="my-3 h-px w-8 bg-white/5" />

      {/* Projects */}
      <nav className="flex flex-col gap-1">
        {PROJECTS_NAV.map((item) => (
          <RailItem key={item.href} item={item} active={isActive(pathname, item.href)} />
        ))}
      </nav>

      {/* Bottom utilities */}
      <div className="mt-auto flex flex-col items-center gap-3 pb-1">
        <Link
          href="/legacy"
          title="Modo demo (fluxo clássico)"
          className="flex h-9 w-9 items-center justify-center rounded-xl text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200"
        >
          <Code2 className="h-[18px] w-[18px]" />
        </Link>
        <button
          title="Status: operacional"
          className="flex h-9 w-9 items-center justify-center rounded-xl text-neon-green transition-colors hover:bg-white/5"
        >
          <Circle className="h-3 w-3 fill-current" />
        </button>
        <button
          title="Conta"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-blue-700 text-xs font-semibold text-white"
        >
          B
        </button>
      </div>
    </aside>
  );
}
