"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  Copy,
  Loader2,
  MoreHorizontal,
  Pencil,
  Share2,
  Trash2,
  Video,
} from "lucide-react";
import { deleteAvatar, renameAvatar } from "@/lib/api";
import { cn } from "@/lib/cn";

interface AvatarMenuProps {
  avatarId: string;
  label?: string | null;
  /** Refresh the surrounding list after a rename/delete. */
  onChanged?: () => void;
  /** Where to go after deleting (looks screen navigates back to /avatar). */
  afterDeleteHref?: string;
  className?: string;
}

export function AvatarMenu({
  avatarId,
  label,
  onChanged,
  afterDeleteHref,
  className,
}: AvatarMenuProps) {
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<"" | "id" | "link">("");
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(label ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setRenaming(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const copy = async (text: string, which: "id" | "link") => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      /* clipboard blocked */
    }
  };

  const submitRename = async () => {
    const next = name.trim();
    if (!next || next === label) {
      setRenaming(false);
      return;
    }
    setBusy(true);
    try {
      await renameAvatar(avatarId, next);
      onChanged?.();
      setOpen(false);
      setRenaming(false);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm("Excluir este avatar? Esta ação não pode ser desfeita.")) return;
    setBusy(true);
    try {
      await deleteAvatar(avatarId);
      setOpen(false);
      if (afterDeleteHref) router.push(afterDeleteHref);
      else onChanged?.();
    } finally {
      setBusy(false);
    }
  };

  const item =
    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-zinc-200 transition-colors hover:bg-white/10";

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        aria-label="Mais ações"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur transition-colors hover:bg-black/70"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>

      {open && (
        <div
          onClick={(e) => e.preventDefault()}
          className="absolute right-0 z-30 mt-1.5 w-56 rounded-xl border border-white/10 bg-[#15151a] p-1.5 shadow-2xl shadow-black/60"
        >
          {renaming ? (
            <div className="p-1">
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitRename();
                  if (e.key === "Escape") setRenaming(false);
                }}
                placeholder="Nome do avatar"
                className="w-full rounded-lg border border-white/10 bg-black/40 px-2.5 py-2 text-sm text-white placeholder:text-zinc-500 focus:border-accent/60 focus:outline-none"
              />
              <div className="mt-2 flex justify-end gap-2">
                <button
                  onClick={() => setRenaming(false)}
                  className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-400 hover:text-white"
                >
                  Cancelar
                </button>
                <button
                  onClick={submitRename}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-obsidian hover:bg-accent-strong"
                >
                  {busy && <Loader2 className="h-3 w-3 animate-spin" />}
                  Salvar
                </button>
              </div>
            </div>
          ) : (
            <>
              <button
                className={item}
                onClick={() => router.push(`/agente?avatar=${avatarId}`)}
              >
                <Video className="h-4 w-4 text-accent" />
                Criar vídeo
              </button>
              <button className={item} onClick={() => setRenaming(true)}>
                <Pencil className="h-4 w-4 text-zinc-400" />
                Editar nome
              </button>
              <button
                className={item}
                onClick={() => copy(`${window.location.origin}/avatar/${avatarId}`, "link")}
              >
                {copied === "link" ? (
                  <Check className="h-4 w-4 text-accent" />
                ) : (
                  <Share2 className="h-4 w-4 text-zinc-400" />
                )}
                {copied === "link" ? "Link copiado" : "Compartilhar"}
              </button>
              <button className={item} onClick={() => copy(avatarId, "id")}>
                {copied === "id" ? (
                  <Check className="h-4 w-4 text-accent" />
                ) : (
                  <Copy className="h-4 w-4 text-zinc-400" />
                )}
                {copied === "id" ? "ID copiado" : "Copiar ID do avatar"}
              </button>
              <div className="my-1 h-px bg-white/10" />
              <button
                className={cn(item, "text-red-300 hover:bg-red-500/10")}
                onClick={remove}
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Excluir
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
