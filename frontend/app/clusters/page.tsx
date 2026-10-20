import AppShell from "@/components/app-shell";
import ClustersPage from "@/components/pages/clusters";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <ClustersPage />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
