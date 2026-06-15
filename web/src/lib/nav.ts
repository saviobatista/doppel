import type { LucideIcon } from "lucide-react";
import {
  Home,
  UserRound,
  Palette,
  LayoutGrid,
  Folder,
  Zap,
  Clapperboard,
  Users,
  AudioLines,
  Sparkles,
} from "lucide-react";

export interface PrimaryNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Top icons of the narrow primary rail. */
export const PRIMARY_NAV: PrimaryNavItem[] = [
  { href: "/", label: "Início", icon: Home },
  { href: "/agente", label: "AI Studio", icon: Sparkles },
  { href: "/avatar", label: "Avatar", icon: UserRound },
  { href: "/marca", label: "Marca", icon: Palette },
  { href: "/apps", label: "Apps", icon: LayoutGrid },
];

export const PROJECTS_NAV: PrimaryNavItem[] = [
  { href: "/projetos", label: "Projetos", icon: Folder },
];

export interface SecondaryNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Extra path prefixes that should also mark this item as active. */
  match?: string[];
}

export interface SecondaryNavGroup {
  label?: string;
  items: SecondaryNavItem[];
}

/** Per-section secondary pane definitions. */
export const AVATAR_PANE: SecondaryNavGroup[] = [
  {
    label: "Vídeos de Avatar",
    items: [
      { href: "/avatar/rapida", label: "Criação rápida", icon: Zap },
      { href: "/avatar/cenas", label: "Cenas do Avatar", icon: Clapperboard },
    ],
  },
  {
    label: "Gerenciar",
    items: [
      { href: "/avatar", label: "Avatares", icon: Users, match: ["/avatar/clonar"] },
      { href: "/avatar/vozes", label: "Vozes", icon: AudioLines },
    ],
  },
];
