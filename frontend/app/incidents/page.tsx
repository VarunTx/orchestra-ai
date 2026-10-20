import AppShell from "@/components/app-shell";
import IncidentsPage from "@/components/pages/incidents";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <IncidentsPage />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
