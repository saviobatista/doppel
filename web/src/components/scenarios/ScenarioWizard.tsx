"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, Copy, Sparkles, X } from "lucide-react";
import { getScenario, type ScenarioStep } from "@/lib/scenarios";
import { cn } from "@/lib/cn";

export function ScenarioWizard({ categoryId }: { categoryId: string }) {
  const router = useRouter();
  const category = getScenario(categoryId);

  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [copied, setCopied] = useState(false);

  const steps = category?.steps ?? [];
  const total = steps.length;
  const onReview = index >= total;

  const prompt = useMemo(
    () => (category && onReview ? category.buildPrompt(answers) : ""),
    [category, onReview, answers],
  );

  if (!category || total === 0) {
    return (
      <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-zinc-400">Esta categoria ainda não está disponível.</p>
        <button
          onClick={() => router.push("/criar")}
          className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-obsidian hover:bg-accent-strong"
        >
          Voltar
        </button>
      </div>
    );
  }

  const step = steps[Math.min(index, total - 1)];
  const selected = answers[step.id] ?? [];
  const canAdvance = onReview || step.optional || step.multi ? true : selected.length > 0;

  const toggle = (value: string) => {
    setAnswers((prev) => {
      const cur = prev[step.id] ?? [];
      if (step.multi) {
        const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
        return { ...prev, [step.id]: next };
      }
      return { ...prev, [step.id]: [value] };
    });
  };

  const next = () => setIndex((i) => Math.min(i + 1, total));
  const back = () => setIndex((i) => Math.max(i - 1, 0));
  const close = () => router.push("/criar");

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* noop */
    }
  };

  const progress = onReview ? 1 : index / total;

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center gap-4 px-6">
        <category.icon className="h-5 w-5 text-accent" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-white">{category.title}</p>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <span className="text-xs text-zinc-500">
            {onReview ? "Revisão" : `Etapa ${index + 1} de ${total}`}
          </span>
          <button
            onClick={close}
            aria-label="Fechar"
            className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </header>

      {/* Progress bar */}
      <div className="h-1 w-full bg-white/5">
        <motion.div
          className="h-full bg-accent"
          animate={{ width: `${Math.round(progress * 100)}%` }}
          transition={{ type: "spring", stiffness: 200, damping: 30 }}
        />
      </div>

      <main className="flex-1 overflow-y-auto px-6 py-8">
        <AnimatePresence mode="wait">
          {!onReview ? (
            <motion.div
              key={step.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="mx-auto w-full max-w-3xl"
            >
              <h1 className="text-2xl font-bold text-white">{step.title}</h1>
              {step.helper && <p className="mt-2 text-sm text-zinc-400">{step.helper}</p>}
              <StepOptions step={step} selected={selected} onToggle={toggle} />
            </motion.div>
          ) : (
            <motion.div
              key="review"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="mx-auto w-full max-w-3xl"
            >
              <h1 className="text-2xl font-bold text-white">Revise seu cenário</h1>
              <p className="mt-2 text-sm text-zinc-400">
                Confira as escolhas e o prompt que vamos usar para gerar seu vídeo.
              </p>

              {/* Choices summary */}
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {steps.map((s) => {
                  const vals = (answers[s.id] ?? [])
                    .map((v) => s.options.find((o) => o.value === v)?.label)
                    .filter(Boolean);
                  return (
                    <div
                      key={s.id}
                      className="rounded-xl border border-white/10 bg-white/5 px-4 py-3"
                    >
                      <p className="text-xs uppercase tracking-wide text-zinc-500">{s.title}</p>
                      <p className="mt-1 text-sm text-zinc-200">
                        {vals.length ? vals.join(", ") : "—"}
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* Generated prompt */}
              <div className="mt-6 rounded-2xl border border-accent/30 bg-accent/5 p-4">
                <div className="flex items-center justify-between">
                  <p className="flex items-center gap-2 text-sm font-semibold text-accent">
                    <Sparkles className="h-4 w-4" />
                    Prompt gerado
                  </p>
                  <button
                    onClick={copyPrompt}
                    className="flex items-center gap-1.5 rounded-full border border-white/10 px-3 py-1 text-xs text-zinc-300 transition-colors hover:bg-white/5"
                  >
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copied ? "Copiado" : "Copiar"}
                  </button>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-zinc-200">{prompt}</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Footer nav */}
      <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-white/5 px-6 py-4">
        <button
          onClick={index === 0 ? close : back}
          className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          {index === 0 ? "Cancelar" : "Voltar"}
        </button>

        {!onReview ? (
          <button
            disabled={!canAdvance}
            onClick={next}
            className={cn(
              "flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-semibold transition-colors",
              canAdvance
                ? "bg-accent text-obsidian hover:bg-accent-strong"
                : "cursor-not-allowed bg-white/10 text-zinc-500",
            )}
          >
            Próximo
            <ArrowRight className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={() => {
              console.info("generate scenario video", { categoryId, answers, prompt });
              router.push("/criar");
            }}
            className="flex items-center gap-2 rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
          >
            <Sparkles className="h-4 w-4" />
            Gerar vídeo
          </button>
        )}
      </footer>
    </div>
  );
}

function StepOptions({
  step,
  selected,
  onToggle,
}: {
  step: ScenarioStep;
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const groups = useMemo(() => {
    const order: string[] = [];
    const map = new Map<string, typeof step.options>();
    for (const opt of step.options) {
      const key = opt.group ?? "";
      if (!map.has(key)) {
        map.set(key, []);
        order.push(key);
      }
      map.get(key)!.push(opt);
    }
    return order.map((key) => ({ key, options: map.get(key)! }));
  }, [step.options]);

  return (
    <div className="mt-6 space-y-6">
      {step.multi && (
        <p className="text-xs text-zinc-500">Selecione uma ou mais opções.</p>
      )}
      {groups.map((g) => (
        <div key={g.key}>
          {g.key && (
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {g.key}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {g.options.map((opt) => {
              const active = selected.includes(opt.value);
              return (
                <button
                  key={opt.value}
                  onClick={() => onToggle(opt.value)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm transition-colors",
                    active
                      ? "border-accent bg-accent/15 font-medium text-white"
                      : "border-white/10 bg-white/5 text-zinc-300 hover:border-white/20 hover:text-white",
                  )}
                >
                  {active && <Check className="h-3.5 w-3.5 text-accent" strokeWidth={3} />}
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
