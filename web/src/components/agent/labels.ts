import {
  AudioLines,
  BarChart3,
  Clapperboard,
  Clock,
  Hash,
  Image as ImageIcon,
  LayoutTemplate,
  ListOrdered,
  Quote,
  Trophy,
  Type,
  type LucideIcon,
} from "lucide-react";

/** PT-BR label for a video-generation progress step published by the worker. */
export function videoStepLabel(step: string | undefined): string {
  if (!step) return "Na fila…";
  if (step === "scripting") return "Preparando o roteiro";
  if (step === "generating_looks") return "Gerando looks do avatar";
  const m = /^component_(\d+)_of_(\d+)$/.exec(step);
  if (m) {
    return m[1] === "1" ? "Renderizando o avatar" : `Gerando cena ${Number(m[1]) - 1}`;
  }
  return step;
}

/** Icon for a design-element overlay kind. */
export function overlayIcon(kind: string): LucideIcon {
  const map: Record<string, LucideIcon> = {
    scoreboard: Trophy,
    score_bug: Trophy,
    stat_card: BarChart3,
    lower_third: LayoutTemplate,
    title_card: Type,
    ticker: ListOrdered,
    timer: Clock,
    quote: Quote,
    bullet_list: ListOrdered,
    logo_bug: Hash,
  };
  return map[kind] ?? LayoutTemplate;
}

export const SCENE_KIND = {
  avatar: { label: "Avatar", icon: Clapperboard, ring: "ring-accent/40", text: "text-accent" },
  broll: { label: "B-roll", icon: ImageIcon, ring: "ring-neon-purple/40", text: "text-neon-purple" },
} as const;

export const transitionLabel: Record<string, string> = {
  cut: "Corte seco",
  crossfade: "Crossfade",
  whip: "Whip pan",
  zoom: "Zoom",
  fade: "Fade",
  slide: "Slide",
};

export const AudioIcon = AudioLines;
