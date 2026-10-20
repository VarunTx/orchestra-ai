import AppShell from "@/components/app-shell";
import NewProjectPage from "@/components/pages/project-new";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <NewProjectPage />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
