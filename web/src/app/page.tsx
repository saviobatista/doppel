import { Workspace } from "@/components/shell/Workspace";
import { SecondarySidebar } from "@/components/shell/SecondarySidebar";
import { HomePane } from "@/components/home/HomePane";
import { NewAgentStarter } from "@/components/agent/NewAgentStarter";
import { FeatureGrid } from "@/components/home/FeatureGrid";

export default function HomePage() {
  return (
    <Workspace
      pane={<SecondarySidebar title="Início" groups={[]} header={<HomePane />} />}
    >
      <div className="mx-auto w-full max-w-5xl px-6 pb-16">
        {/* Same composer as AI Studio */}
        <NewAgentStarter />

        {/* Feature grid */}
        <section className="mt-4">
          <FeatureGrid />
        </section>
      </div>
    </Workspace>
  );
}
