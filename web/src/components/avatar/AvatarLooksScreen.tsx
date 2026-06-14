"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  Sparkles,
  Upload,
  Video,
  X,
} from "lucide-react";
import { getAvatar, type AvatarDetail, type AvatarLook } from "@/lib/api";
import { AvatarMenu } from "@/components/avatar/AvatarMenu";
import { LiveAvatarVideo } from "@/components/avatar/LiveAvatarVideo";

type Selected =
  | { kind: "original" }
  | { kind: "look"; look: AvatarLook; index: number }
  | null;

export function AvatarLooksScreen({ avatarId }: { avatarId: string }) {
  const router = useRouter();
  const [detail, setDetail] = useState<AvatarDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Selected>(null);

  useEffect(() => {
    let active = true;
    getAvatar(avatarId)
      .then((d) => active && setDetail(d))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [avatarId]);

  const name = detail?.label?.trim() || "Avatar";
  const looks = detail?.looks ?? [];
  const lookCount = looks.length + (detail?.preview_url ? 1 : 0);
  const processing = detail != null && detail.status !== "ready";

  const openStudio = (lookIndex?: number) => {
    const q = lookIndex != null ? `?avatar=${avatarId}&look=${lookIndex}` : `?avatar=${avatarId}`;
    router.push(`/agente${q}`);
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={() => router.push("/avatar")}
            aria-label="Voltar"
            className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-white"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <h1 className="truncate text-base font-semibold text-white">{name}</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => openStudio()}
            className="flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
          >
            <Video className="h-4 w-4" />
            Criar vídeo
          </button>
          {detail && (
            <AvatarMenu avatarId={avatarId} label={detail.label} afterDeleteHref="/avatar" />
          )}
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-6 pb-12">
        {error ? (
          <div className="mx-auto mt-16 max-w-md text-center text-sm text-zinc-400">{error}</div>
        ) : !detail ? (
          <div className="flex justify-center py-24">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
          </div>
        ) : (
          <>
            <p className="mb-4 text-sm font-medium text-zinc-400">
              {lookCount} {lookCount === 1 ? "visual" : "visuais"}
            </p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              <ActionTile icon={Sparkles} label="Criar com IA" note="Em breve" />
              <ActionTile icon={Upload} label="Carregar look" note="Em breve" />

              {detail.preview_url && (
                <LookTile
                  url={detail.preview_url}
                  label={name}
                  badge="Original"
                  onClick={() => setSelected({ kind: "original" })}
                />
              )}

              {looks.map((look, i) => (
                <LookTile
                  key={i}
                  url={look.url}
                  label={look.label ?? `Visual ${i + 1}`}
                  onClick={() => setSelected({ kind: "look", look, index: i })}
                />
              ))}

              {processing &&
                Array.from({ length: Math.max(0, 2 - looks.length) }).map((_, i) => (
                  <div
                    key={`p${i}`}
                    className="flex aspect-[3/4] items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03]"
                  >
                    <Loader2 className="h-5 w-5 animate-spin text-zinc-600" />
                  </div>
                ))}
            </div>
          </>
        )}
      </main>

      {selected && detail && (
        <LookModal
          name={name}
          selected={selected}
          hello={detail.hello_url ?? null}
          idle={detail.idle_url ?? null}
          fallback={detail.preview_url ?? null}
          onClose={() => setSelected(null)}
          onUse={() =>
            openStudio(selected.kind === "look" ? selected.index : undefined)
          }
        />
      )}
    </div>
  );
}

function ActionTile({
  icon: Icon,
  label,
  note,
}: {
  icon: typeof Sparkles;
  label: string;
  note?: string;
}) {
  return (
    <button
      disabled
      className="flex aspect-[3/4] cursor-not-allowed flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/15 bg-white/[0.02] text-zinc-400"
    >
      <Icon className="h-6 w-6" />
      <span className="text-sm font-medium">{label}</span>
      {note && <span className="text-[11px] text-zinc-600">{note}</span>}
    </button>
  );
}

function LookTile({
  url,
  label,
  badge,
  onClick,
}: {
  url: string;
  label: string;
  badge?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="group relative aspect-[3/4] overflow-hidden rounded-2xl border border-white/10 bg-black text-left transition-colors hover:border-accent/50"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={label}
        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
      />
      {badge && (
        <span className="absolute left-2 top-2 rounded-full bg-accent/90 px-2 py-0.5 text-[10px] font-semibold text-obsidian">
          {badge}
        </span>
      )}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2.5">
        <p className="truncate text-xs font-medium text-white">{label}</p>
      </div>
    </button>
  );
}

function LookModal({
  name,
  selected,
  hello,
  idle,
  fallback,
  onClose,
  onUse,
}: {
  name: string;
  selected: NonNullable<Selected>;
  hello: string | null;
  idle: string | null;
  fallback: string | null;
  onClose: () => void;
  onUse: () => void;
}) {
  const isOriginal = selected.kind === "original";
  const title = isOriginal ? name : selected.look.label ?? name;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm overflow-hidden rounded-2xl border border-white/10 bg-[#15151a] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3">
          <h3 className="truncate text-sm font-semibold text-white">{title}</h3>
          <button
            onClick={onClose}
            aria-label="Fechar"
            className="flex h-8 w-8 items-center justify-center rounded-full text-zinc-400 hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="bg-black">
          {isOriginal && hello ? (
            <LiveAvatarVideo key={hello} helloUrl={hello} idleUrl={idle} />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={isOriginal ? (fallback ?? "") : selected.look.url}
              alt={title}
              className="aspect-[9/16] w-full object-cover"
            />
          )}
        </div>

        <div className="flex justify-end p-3">
          <button
            onClick={onUse}
            className="flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
          >
            <Video className="h-4 w-4" />
            Usar no vídeo
          </button>
        </div>
      </div>
    </div>
  );
}
