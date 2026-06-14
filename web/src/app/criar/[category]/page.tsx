import { ScenarioWizard } from "@/components/scenarios/ScenarioWizard";

export const metadata = {
  title: "Doppel — Montar cenário",
};

export default async function CategoryWizardPage({
  params,
}: {
  params: Promise<{ category: string }>;
}) {
  const { category } = await params;
  return <ScenarioWizard categoryId={category} />;
}
