import AppShell from "@/components/app-shell";
import IntegrationsPage from "@/components/pages/integrations";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <IntegrationsPage />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
