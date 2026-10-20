import AppShell from "@/components/app-shell";
import ControlPlane from "@/components/control-plane";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <ControlPlane environment={environment} embedded initialView="Executions" />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
