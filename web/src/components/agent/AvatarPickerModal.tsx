"use client";

import { useEffect, useState } from "react";
import { Check, LayoutGrid, List, UserRound, X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { AvatarItem } from "@/lib/api";

type View = "grid" | "list";

interface Props {
  avatars: AvatarItem[];
  /** Current selection encoded as avatarId or avatarId#lookIndex. */
  value: string;
  onSelect: (avatarId: string, lookIndex: number | null) => void;
  onClose: () => void;
}

function enc(avatarId: string, lookIndex: number | null): string {
  return lookIndex == null ? avatarId : `${avatarId}#${lookIndex}`;
}

export function AvatarPickerModal({ avatars, value, onSelect, onClose }: Props) {
  const [view, setView] = useState<View>("grid");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pick = (avatarId: string, lookIndex: number | null) => {
    onSelect(avatarId, lookIndex);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="relative flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-white/10 bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/5 px-6 py-4">
          <h2 className="text-lg font-bold text-white">Escolher avatar</h2>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-white/10 bg-white/5 p-0.5">
              <ViewToggle active={view === "grid"} onClick={() => setView("grid")} icon={LayoutGrid}>
                Grade
              </ViewToggle>
              <ViewToggle active={view === "list"} onClick={() => setView("list")} icon={List}>
                Lista
              </ViewToggle>
            </div>
            <button
              onClick={onClose}
              aria-label="Fechar"
              className="flex h-8 w-8 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-6 py-5">
          {avatars.length === 0 ? (
            <p className="py-12 text-center text-sm text-zinc-500">
              Nenhum avatar pronto. Crie um em Avatar → Novo Avatar.
            </p>
          ) : view === "grid" ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              {avatars.map((a, i) => (
                <GridCard
                  key={a.avatar_id}
                  avatar={a}
                  index={i}
                  value={value}
                  onPick={pick}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col divide-y divide-white/5">
              {avatars.map((a, i) => (
                <ListRow
                  key={a.avatar_id}
                  avatar={a}
                  index={i}
                  value={value}
                  onPick={pick}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function name(a: AvatarItem, i: number): string {
  return a.label?.trim() || `Avatar ${i + 1}`;
}

function Thumb({ url, className }: { url?: string | null; className?: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className={cn("object-cover", className)} />;
  }
  return (
    <div className={cn("flex items-center justify-center bg-white/5", className)}>
      <UserRound className="h-1/3 w-1/3 text-zinc-600" />
    </div>
  );
}

function GridCard({
  avatar,
  index,
  value,
  onPick,
}: {
  avatar: AvatarItem;
  index: number;
  value: string;
  onPick: (a: string, l: number | null) => void;
}) {
  const looks = avatar.looks ?? [];
  const baseSelected = value === enc(avatar.avatar_id, null);
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border bg-black/30 transition-colors",
        baseSelected ? "border-accent/60" : "border-white/10 hover:border-white/25",
      )}
    >
      <button
        onClick={() => onPick(avatar.avatar_id, null)}
        className="relative block aspect-[4/5] w-full"
      >
        <Thumb url={avatar.preview_url} className="h-full w-full" />
        {baseSelected && (
          <span className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-obsidian">
            <Check className="h-3.5 w-3.5" />
          </span>
        )}
      </button>
      <div className="px-2.5 py-2">
        <p className="truncate text-sm font-semibold text-white">{name(avatar, index)}</p>
        {looks.length > 0 && (
          <div className="mt-1.5 flex gap-1">
            {looks.slice(0, 5).map((lk, j) => {
              const sel = value === enc(avatar.avatar_id, j);
              return (
                <button
                  key={j}
                  onClick={() => onPick(avatar.avatar_id, j)}
                  title={lk.label ?? `Visual ${j + 1}`}
                  className={cn(
                    "h-8 w-8 shrink-0 overflow-hidden rounded-md border",
                    sel ? "border-accent" : "border-white/10 hover:border-white/30",
                  )}
                >
                  <Thumb url={lk.url} className="h-full w-full" />
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function ListRow({
  avatar,
  index,
  value,
  onPick,
}: {
  avatar: AvatarItem;
  index: number;
  value: string;
  onPick: (a: string, l: number | null) => void;
}) {
  const looks = avatar.looks ?? [];
  const baseSelected = value === enc(avatar.avatar_id, null);
  return (
    <div className="flex items-center gap-3 py-3">
      <button
        onClick={() => onPick(avatar.avatar_id, null)}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-1.5 text-left transition-colors",
          baseSelected ? "bg-accent/10" : "hover:bg-white/5",
        )}
      >
        <Thumb url={avatar.preview_url} className="h-12 w-12 shrink-0 rounded-full" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-white">{name(avatar, index)}</p>
          <p className="text-xs text-zinc-500">
            {looks.length > 0 ? `${looks.length} looks` : "Avatar"}
          </p>
        </div>
        {baseSelected && <Check className="ml-auto h-4 w-4 shrink-0 text-accent" />}
      </button>
      {looks.length > 0 && (
        <div className="flex gap-1.5">
          {looks.slice(0, 7).map((lk, j) => {
            const sel = value === enc(avatar.avatar_id, j);
            return (
              <button
                key={j}
                onClick={() => onPick(avatar.avatar_id, j)}
                title={lk.label ?? `Visual ${j + 1}`}
                className={cn(
                  "h-12 w-12 shrink-0 overflow-hidden rounded-lg border",
                  sel ? "border-accent" : "border-white/10 hover:border-white/30",
                )}
              >
                <Thumb url={lk.url} className="h-full w-full" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ViewToggle({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof List;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
        active ? "bg-white/10 text-white" : "text-zinc-400 hover:text-zinc-200",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  );
}
