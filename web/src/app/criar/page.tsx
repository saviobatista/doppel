import { Workspace } from "@/components/shell/Workspace";
import { CategoryGrid } from "@/components/scenarios/CategoryGrid";

export const metadata = {
  title: "Doppel — Criar vídeo com cenário",
};

export default function CriarPage() {
  return (
    <Workspace>
      <CategoryGrid />
    </Workspace>
  );
}
