"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { listAvatars, type AvatarItem } from "@/lib/api";
import { AvatarTabs } from "@/components/avatar/AvatarTabs";
import { AvatarGrid } from "@/components/avatar/AvatarGrid";
import { CreateAvatarPanel } from "@/components/avatar/CreateAvatarPanel";
import { ComingSoon } from "@/components/shell/ComingSoon";

type TabId = "meus" | "publicos";

export function AvatarHome() {
  const [avatars, setAvatars] = useState<AvatarItem[] | null>(null);
  const [tab, setTab] = useState<TabId>("meus");

  const reload = useCallback(() => {
    listAvatars()
      .then(setAvatars)
      .catch(() => setAvatars([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // No avatars yet → the avatar screen *is* the creation screen.
  if (avatars !== null && avatars.length === 0) {
    return (
      <div>
        <AvatarTabs value={tab} onChange={setTab} />
        {tab === "meus" ? (
          <CreateAvatarPanel />
        ) : (
          <ComingSoon title="Avatares Públicos" note="Em breve: uma galeria de avatares prontos." />
        )}
      </div>
    );
  }

  return (
    <div>
      <AvatarTabs value={tab} onChange={setTab} />
      {tab === "publicos" ? (
        <ComingSoon title="Avatares Públicos" note="Em breve: uma galeria de avatares prontos." />
      ) : avatars === null ? (
        <div className="flex justify-center py-24">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        </div>
      ) : (
        <AvatarGrid avatars={avatars} onChanged={reload} />
      )}
    </div>
  );
}
