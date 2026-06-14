import { Workspace } from "@/components/shell/Workspace";

const LEGACY_URL = process.env.NEXT_PUBLIC_LEGACY_URL ?? "http://localhost:5180";

export const metadata = {
  title: "Doppel — Fluxo clássico (demo)",
};

export default function LegacyPage() {
  return (
    <Workspace>
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-white/5 px-6 py-2 text-xs text-zinc-500">
          <span className="rounded-full bg-white/5 px-2 py-0.5 text-zinc-400">
            Referência
          </span>
          Fluxo cinematográfico original (app Vite) — preservado para consulta.
        </div>
        <iframe
          src={LEGACY_URL}
          title="Fluxo clássico Doppel"
          className="min-h-0 flex-1 border-0 bg-black"
        />
      </div>
    </Workspace>
  );
}
