import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Conductor — Control Plane",
  description:
    "Observe, orchestrate, and debug real AI workflows with Conductor OSS.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
