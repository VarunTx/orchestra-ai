import ControlPlane from "@/components/control-plane";
export default function Home() {
  return (
    <ControlPlane
      environment={
        process.env.DEPLOYMENT_ENVIRONMENT === "hosted" ? "hosted" : "local"
      }
    />
  );
}
export const dynamic = "force-dynamic";
