import { PrimarySidebar } from "./PrimarySidebar";

/**
 * Top-level chrome: the persistent narrow rail + a flex slot for each page's
 * workspace (optional secondary pane + main content column).
 */
export function AppFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh overflow-hidden bg-obsidian">
      <PrimarySidebar />
      <div className="flex min-w-0 flex-1">{children}</div>
    </div>
  );
}
