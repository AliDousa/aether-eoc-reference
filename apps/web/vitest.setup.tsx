import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

// jsdom implements neither of these, and both are touched by Recharts'
// ResponsiveContainer and by the WebSocket hook.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverStub);

if (!("WebSocket" in globalThis)) {
  vi.stubGlobal(
    "WebSocket",
    class {
      static readonly OPEN = 1;
      close() {}
      send() {}
    },
  );
}

// Recharts measures its container; jsdom reports 0x0 and logs a warning for
// every chart. Give ResponsiveContainer a fixed size under test so the output
// stays readable and the charts still render their children.
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <actual.ResponsiveContainer width={800} height={300}>
        {children as React.ReactElement}
      </actual.ResponsiveContainer>
    ),
  };
});
