/**
 * The Zod resolver is first-party code (see lib/form.ts for why), so it is
 * tested rather than trusted. The contract React Hook Form relies on is
 * narrow: return parsed values OR field errors, never both, and key the errors
 * by dotted field path.
 */

import { describe, expect, it } from "vitest";
import { z } from "zod";

import { zodResolver } from "@/lib/form";

const schema = z.object({
  sku_id: z.string().min(1, "Choose a resource."),
  quantity: z.coerce.number().int().positive("Quantity must be a positive whole number."),
  justification: z.string().min(12, "Say why this is needed."),
});

type Values = z.input<typeof schema>;

// React Hook Form passes context and options; the resolver ignores both.
const resolve = (values: unknown) =>
  zodResolver<Values>(schema)(
    values as Values,
    undefined,
    {} as Parameters<ReturnType<typeof zodResolver<Values>>>[2],
  );

describe("zodResolver", () => {
  it("returns parsed values and no errors when input is valid", async () => {
    const result = await resolve({
      sku_id: "sku_ors",
      quantity: "400", // strings arrive from number inputs; coerce handles it
      justification: "Sector North is below its reorder point.",
    });

    expect(result.errors).toEqual({});
    expect(result.values).toMatchObject({ sku_id: "sku_ors", quantity: 400 });
  });

  it("returns field errors keyed by path, and no values, when input is invalid", async () => {
    const result = await resolve({ sku_id: "", quantity: -5, justification: "too short" });

    expect(result.values).toEqual({});
    const errors = result.errors as Record<string, { type: string; message: string }>;

    expect(errors.sku_id?.message).toBe("Choose a resource.");
    expect(errors.quantity?.message).toBe("Quantity must be a positive whole number.");
    expect(errors.justification?.message).toBe("Say why this is needed.");
    // Every error carries a type, which RHF uses for error-type matching.
    expect(errors.sku_id?.type).toBeTruthy();
  });

  it("keeps only the first error per field", async () => {
    // An empty string fails both min(1) and, after coercion elsewhere, would
    // fail more rules; the form should still show exactly one message.
    const result = await resolve({ sku_id: "", quantity: 1, justification: "" });
    const errors = result.errors as Record<string, unknown>;

    expect(Object.keys(errors).sort()).toEqual(["justification", "sku_id"]);
  });

  it("reports a missing field rather than throwing", async () => {
    const result = await resolve({});
    expect(result.values).toEqual({});
    expect(Object.keys(result.errors).length).toBeGreaterThan(0);
  });
});
