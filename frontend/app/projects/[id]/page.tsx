import AppShell from "@/components/app-shell";
import ProjectDetail from "@/components/pages/project-detail";
import { environment } from "@/lib/environment";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell environment={environment}>
      <ProjectDetail id={id} />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
