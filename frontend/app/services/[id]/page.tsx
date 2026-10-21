import AppShell from "@/components/app-shell";
import ServiceDetail from "@/components/pages/service-detail";
import { environment } from "@/lib/environment";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell environment={environment}>
      <ServiceDetail id={id} />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
