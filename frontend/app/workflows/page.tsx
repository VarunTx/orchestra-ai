import AppShell from "@/components/app-shell";
import ControlPlane from "@/components/control-plane";
import WorkflowCatalog from "@/components/pages/workflow-catalog";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <ControlPlane environment={environment} embedded initialView="Workflows" />
      <section className="content" style={{ paddingTop: 0 }}>
        <WorkflowCatalog />
      </section>
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
