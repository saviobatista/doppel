"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Play, UserRound } from "lucide-react";
import type { AvatarItem } from "@/lib/api";
import { AvatarMenu } from "@/components/avatar/AvatarMenu";
import { cn } from "@/lib/cn";

export function AvatarGrid({
  avatars,
  onChanged,
}: {
  avatars: AvatarItem[];
  onChanged?: () => void;
}) {
  return (
    <div className="px-8 py-8">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {avatars.map((a) => (
          <AvatarCard key={a.avatar_id} avatar={a} onChanged={onChanged} />
        ))}
      </div>
    </div>
  );
}

function AvatarCard({ avatar, onChanged }: { avatar: AvatarItem; onChanged?: () => void }) {
  const router = useRouter();
  const name = avatar.label?.trim() || "Avatar sem nome";
  const looks = avatar.looks ?? [];
  const processing = avatar.status !== "ready";

  return (
    <div className="group">
      <Link href={`/avatar/${avatar.avatar_id}`} className="block">
        <div className="relative flex gap-1.5 overflow-hidden rounded-2xl border border-white/10 bg-panel/40 transition-colors group-hover:border-accent/40">
          {/* First frame */}
          <div className="relative aspect-[3/4] flex-[2] bg-black">
            {avatar.preview_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={avatar.preview_url} alt={name} className="h-full w-full object-cover" />
            ) : (
              <Placeholder icon />
            )}
            {processing && (
              <span className="absolute left-2 top-2 flex items-center gap-1.5 rounded-full bg-black/60 px-2 py-1 text-[11px] font-medium text-white backdrop-blur">
                <Loader2 className="h-3 w-3 animate-spin" />
                Preparando
              </span>
            )}
          </div>

          {/* Two auto-generated looks */}
          <div className="flex flex-[1] flex-col gap-1.5">
            {[0, 1].map((i) => {
              const look = looks[i];
              return (
                <div key={i} className="relative flex-1 overflow-hidden bg-black/60">
                  {look ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={look.url}
                      alt={look.label ?? ""}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <Placeholder pulse={processing} />
                  )}
                </div>
              );
            })}
          </div>

          {/* Hover actions */}
          <div className="absolute right-2 top-2 flex items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
            {!processing && (
              <button
                onClick={(e) => {
                  e.preventDefault();
                  router.push(`/agente?avatar=${avatar.avatar_id}`);
                }}
                aria-label="Criar vídeo"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-obsidian transition-colors hover:bg-accent-strong"
              >
                <Play className="h-4 w-4 fill-current" />
              </button>
            )}
            <AvatarMenu avatarId={avatar.avatar_id} label={avatar.label} onChanged={onChanged} />
          </div>
        </div>
      </Link>

      <div className="mt-2.5 flex items-center justify-between">
        <p className="truncate text-sm font-semibold text-white">{name}</p>
        {avatar.voice_id && (
          <span className="shrink-0 rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-medium text-zinc-400">
            Voz
          </span>
        )}
      </div>
    </div>
  );
}

function Placeholder({ icon, pulse }: { icon?: boolean; pulse?: boolean }) {
  return (
    <div
      className={cn(
        "flex h-full w-full items-center justify-center bg-gradient-to-br from-white/5 to-white/0",
        pulse && "animate-pulse",
      )}
    >
      {icon && <UserRound className="h-6 w-6 text-zinc-600" />}
    </div>
  );
}
