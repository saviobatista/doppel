"use client";

import { useParams, useSearchParams } from "next/navigation";
import { AvatarPane } from "@/components/avatar/AvatarPane";
import { AvatarReadyScreen } from "@/components/avatar/AvatarReadyScreen";
import { AvatarLooksScreen } from "@/components/avatar/AvatarLooksScreen";

export default function AvatarDetailPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  // The creation flow lands here with ?new=1 to finish voice setup; clicking an
  // existing avatar card lands here without it and shows the looks gallery.
  const isNew = search.get("new") === "1";
  return (
    <>
      <AvatarPane />
      {isNew ? (
        <AvatarReadyScreen avatarId={params.id} />
      ) : (
        <AvatarLooksScreen avatarId={params.id} />
      )}
    </>
  );
}
