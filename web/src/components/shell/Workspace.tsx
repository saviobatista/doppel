import { TopBar } from "./TopBar";

/**
 * A page workspace: optional secondary sidebar pane + the main scrollable
 * content column (which carries the top-right utility header).
 */
export function Workspace({
  pane,
  actions,
  children,
}: {
  pane?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      {pane}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar actions={actions} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </>
  );
}
