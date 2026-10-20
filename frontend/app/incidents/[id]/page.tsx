import AppShell from "@/components/app-shell";
import IncidentDetail from "@/components/pages/incident-detail";
import { environment } from "@/lib/environment";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell environment={environment}>
      <IncidentDetail id={id} />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
