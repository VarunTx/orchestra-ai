import AppShell from "@/components/app-shell";
import ServicesPage from "@/components/pages/services";
import { environment } from "@/lib/environment";

export default function Page() {
  return (
    <AppShell environment={environment}>
      <ServicesPage />
    </AppShell>
  );
}
export const dynamic = "force-dynamic";
