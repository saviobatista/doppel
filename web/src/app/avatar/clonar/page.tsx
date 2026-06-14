import { AvatarPane } from "@/components/avatar/AvatarPane";
import { CloneAvatarSetup } from "@/components/avatar/CloneAvatarSetup";

export const metadata = {
  title: "Doppel — Clonar uma pessoa real",
};

export default function ClonarPage() {
  return (
    <>
      <AvatarPane />
      <CloneAvatarSetup />
    </>
  );
}
