"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

const TABS = [
  { id: "meus", label: "Meus Avatares" },
  { id: "publicos", label: "Avatares Públicos" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function AvatarTabs({
  value,
  onChange,
}: {
  value?: TabId;
  onChange?: (id: TabId) => void;
} = {}) {
  const [internal, setInternal] = useState<TabId>("meus");
  const active = value ?? internal;
  const setActive = onChange ?? setInternal;

  return (
    <div className="flex items-center gap-6 border-b border-white/5 px-8">
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => setActive(t.id)}
          className={cn(
            "relative py-3 text-sm font-medium transition-colors",
            active === t.id ? "text-white" : "text-zinc-500 hover:text-zinc-300",
          )}
        >
          {t.label}
          {active === t.id && (
            <motion.span
              layoutId="avatar-tab"
              className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-accent"
              transition={{ type: "spring", stiffness: 500, damping: 40 }}
            />
          )}
        </button>
      ))}
    </div>
  );
}
