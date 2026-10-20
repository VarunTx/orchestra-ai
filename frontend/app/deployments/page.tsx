import AppShell from "@/components/app-shell";
import DeploymentsPage from "@/components/pages/deployments";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <DeploymentsPage />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
