import { Workspace } from "@/components/shell/Workspace";
import { FeaturedApps } from "@/components/apps/FeaturedApps";
import { AppCatalog } from "@/components/apps/AppCatalog";

export default function AppsPage() {
  return (
    <Workspace>
      <div className="mx-auto w-full max-w-6xl px-8 pb-16">
        <section className="pt-6">
          <h1 className="text-2xl font-bold text-white">Biblioteca de Apps</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Ferramentas de IA para criar, editar e traduzir vídeos.
          </p>
          <div className="mt-6">
            <FeaturedApps />
          </div>
        </section>

        <section className="mt-10">
          <AppCatalog />
        </section>
      </div>
    </Workspace>
  );
}
