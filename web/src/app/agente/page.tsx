import { Workspace } from "@/components/shell/Workspace";
import { NewAgentStarter } from "@/components/agent/NewAgentStarter";

export const metadata = {
  title: "Doppel — Agente de Vídeo",
};

export default async function AgenteStarterPage({
  searchParams,
}: {
  searchParams: Promise<{ avatar?: string; look?: string }>;
}) {
  const { avatar, look } = await searchParams;
  const lookIndex = look != null && look !== "" ? Number(look) : null;
  return (
    <Workspace>
      <NewAgentStarter
        initialAvatarId={avatar}
        initialLook={Number.isFinite(lookIndex) ? lookIndex : null}
      />
    </Workspace>
  );
}
