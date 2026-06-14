import Link from "next/link";
import { UserPlus } from "lucide-react";
import { Workspace } from "@/components/shell/Workspace";
import { AvatarPane } from "@/components/avatar/AvatarPane";

export default function AvatarLayout({ children }: { children: React.ReactNode }) {
  return (
    <Workspace
      pane={<AvatarPane />}
      actions={
        <Link
          href="/avatar/clonar"
          className="flex items-center gap-2 rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-obsidian transition-colors hover:bg-accent-strong"
        >
          <UserPlus className="h-4 w-4" />
          Novo Avatar
        </Link>
      }
    >
      {children}
    </Workspace>
  );
}
