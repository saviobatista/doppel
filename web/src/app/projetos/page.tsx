import { Workspace } from "@/components/shell/Workspace";
import { ProjectsGrid } from "@/components/projects/ProjectsGrid";

export const metadata = {
  title: "Doppel — Projetos",
};

export default function ProjetosPage() {
  return (
    <Workspace>
      <ProjectsGrid />
    </Workspace>
  );
}
