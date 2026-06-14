import { Workspace } from "@/components/shell/Workspace";
import { SecondarySidebar } from "@/components/shell/SecondarySidebar";
import { HomePane } from "@/components/home/HomePane";
import { PromptBar } from "@/components/home/PromptBar";
import { FeatureGrid } from "@/components/home/FeatureGrid";

export default function HomePage() {
  return (
    <Workspace
      pane={<SecondarySidebar title="Início" groups={[]} header={<HomePane />} />}
    >
      <div className="mx-auto w-full max-w-5xl px-6 pb-16">
        {/* Hero */}
        <section className="flex flex-col items-center pt-10 text-center sm:pt-16">
          <div className="relative">
            <div className="pointer-events-none absolute -inset-x-24 -top-10 -z-10 h-40 bg-[radial-gradient(50%_100%_at_50%_50%,rgba(56,189,248,0.22),rgba(168,85,247,0.12),transparent_70%)] blur-2xl" />
            <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
              Diga com vídeo
            </h1>
          </div>
          <p className="mt-3 text-sm text-zinc-400 sm:text-base">
            O novo agente all-in-one da Doppel para criação de vídeos
          </p>

          <div className="mt-8 flex w-full justify-center">
            <PromptBar />
          </div>
        </section>

        {/* Feature grid */}
        <section className="mt-12">
          <FeatureGrid />
        </section>
      </div>
    </Workspace>
  );
}
