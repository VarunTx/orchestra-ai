import AppShell from "@/components/app-shell";
import Overview from "@/components/pages/overview";

export default function Home() {
  return (
    <AppShell
      environment={
        process.env.DEPLOYMENT_ENVIRONMENT === "hosted" ? "hosted" : "local"
      }
    >
      <Overview />
    </AppShell>
  );
}

export const dynamic = "force-dynamic";
