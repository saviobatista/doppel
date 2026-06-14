"use client";

import { useParams } from "next/navigation";
import { AgentScreen } from "@/components/agent/AgentScreen";

export default function AgentePage() {
  const params = useParams<{ id: string }>();
  return <AgentScreen planId={params.id} />;
}
