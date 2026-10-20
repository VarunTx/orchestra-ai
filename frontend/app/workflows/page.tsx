import AppShell from "@/components/app-shell";
import ControlPlane from "@/components/control-plane";
import WorkflowCatalog from "@/components/pages/workflow-catalog";
import EngineTelemetry from "@/components/pages/engine-telemetry";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <ControlPlane environment={environment} embedded initialView="Workflows" />
      <section className="content" style={{ paddingTop: 0 }}>
        <WorkflowCatalog />
        <EngineTelemetry />
      </section>
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
