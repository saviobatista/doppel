import { Workspace } from "@/components/shell/Workspace";
import { NewAgentStarter } from "@/components/agent/NewAgentStarter";

export const metadata = {
  title: "Doppel — Agente de Vídeo",
};

export default async function AgenteStarterPage({
  searchParams,
}: {
  searchParams: Promise<{ avatar?: string }>;
}) {
  const { avatar } = await searchParams;
  return (
    <Workspace>
      <NewAgentStarter initialAvatarId={avatar} />
    </Workspace>
  );
}
