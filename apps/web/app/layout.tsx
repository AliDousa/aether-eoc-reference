import type { Metadata, Viewport } from "next";

import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Aether EOC — Reference Slice (Synthetic Demo)",
  description:
    "Reference slice of a next-generation public-health Emergency Operations Center: live ICS board, resource requests, human-in-the-loop AI agents, and an append-only audit log. Synthetic data only.",
  // A public demo containing fictional incident data has no business in search
  // results, where it could be mistaken for a real operational system.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#0a0e14",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
