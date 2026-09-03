"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";

import { SessionProvider } from "@/lib/session";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // The WebSocket drives freshness; the interval is the safety net for
            // when the socket is down, which is exactly when a stale board is
            // most dangerous.
            refetchInterval: 20_000,
            refetchOnWindowFocus: true,
            staleTime: 2_000,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <SessionProvider>{children}</SessionProvider>
    </QueryClientProvider>
  );
}
