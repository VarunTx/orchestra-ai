import AppShell from "@/components/app-shell";
import ProjectsPage from "@/components/pages/projects";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <ProjectsPage />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
