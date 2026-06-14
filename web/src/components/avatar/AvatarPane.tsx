"use client";

import { SecondarySidebar } from "@/components/shell/SecondarySidebar";
import { AVATAR_PANE } from "@/lib/nav";

export function AvatarPane() {
  return <SecondarySidebar title="Vídeos de Avatar" groups={AVATAR_PANE} />;
}
