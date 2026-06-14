import { Construction } from "lucide-react";

export function ComingSoon({ title, note }: { title: string; note?: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 py-24 text-center">
      <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-zinc-400">
        <Construction className="h-6 w-6" />
      </span>
      <h2 className="text-xl font-semibold text-white">{title}</h2>
      <p className="mt-1.5 max-w-sm text-sm text-zinc-500">
        {note ?? "Esta seção faz parte da estrutura e será construída em seguida."}
      </p>
    </div>
  );
}
