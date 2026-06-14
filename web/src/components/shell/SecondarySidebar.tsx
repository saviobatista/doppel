"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose } from "lucide-react";
import type { SecondaryNavGroup } from "@/lib/nav";
import { cn } from "@/lib/cn";

interface SecondarySidebarProps {
  title: string;
  groups: SecondaryNavGroup[];
  /** Optional custom block rendered above the nav groups (e.g. onboarding). */
  header?: React.ReactNode;
  /** Optional custom block rendered below the nav groups (e.g. recents). */
  footer?: React.ReactNode;
}

export function SecondarySidebar({ title, groups, header, footer }: SecondarySidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="hidden h-dvh w-60 shrink-0 flex-col border-r border-white/5 bg-panel/30 md:flex">
      <div className="flex h-14 items-center justify-between px-4">
        <span className="text-sm font-semibold text-zinc-200">{title}</span>
        <button className="text-zinc-500 transition-colors hover:text-zinc-200">
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {header && <div className="mb-3">{header}</div>}

        {groups.map((group, gi) => (
          <div key={gi} className="mb-4">
            {group.label && (
              <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-600">
                {group.label}
              </p>
            )}
            <nav className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const active =
                  pathname === item.href ||
                  (item.match?.some(
                    (m) => pathname === m || pathname.startsWith(m + "/"),
                  ) ??
                    false);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                      active
                        ? "bg-accent/15 font-medium text-accent"
                        : "text-zinc-400 hover:bg-white/5 hover:text-zinc-100",
                    )}
                  >
                    <Icon className="h-[18px] w-[18px]" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        ))}

        {footer}
      </div>
    </aside>
  );
}
