"use client";

/**
 * Request queue plus the create form.
 *
 * The form is React Hook Form + Zod: the same constraints the API enforces,
 * declared once on the client so an operator gets told before the round trip
 * rather than after. The server remains the authority — client validation is a
 * courtesy, not a control.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Loader2, Plus, X } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { RequestsTable } from "@/components/requests-table";
import type { ViewRole } from "@/components/requests-table";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/format";
import { Permission, useSession } from "@/lib/session";

const schema = z.object({
  sku_id: z.string().min(1, "Choose a resource."),
  quantity: z.coerce.number().int().positive("Quantity must be a positive whole number."),
  priority: z.enum(["routine", "priority", "immediate"]),
  requesting_section: z.enum(["command", "operations", "planning", "logistics"]),
  destination_site_id: z.string().min(1, "Choose a destination."),
  justification: z
    .string()
    .min(12, "Say why this is needed — a justification is part of the record."),
});

type FormValues = z.input<typeof schema>;

const FILTERS = ["all", "open", "needs decision", "closed"] as const;
type Filter = (typeof FILTERS)[number];

export default function RequestsPage() {
  const { session, can } = useSession();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [showForm, setShowForm] = useState(false);

  const { data, isLoading } = useQuery({ queryKey: ["requests"], queryFn: api.requests });
  const { data: skus } = useQuery({ queryKey: ["skus"], queryFn: api.skus });
  const { data: sites } = useQuery({ queryKey: ["sites"], queryFn: api.sites });

  const role = session?.operator.ics_role;
  const viewRole: ViewRole =
    role === "operations_section" || role === "logistics_section" ? role : "incident_commander";

  const requests = (data?.requests ?? []).filter((request) => {
    switch (filter) {
      case "open":
        return request.is_open;
      case "needs decision":
        return request.recommendation?.status === "pending";
      case "closed":
        return !request.is_open;
      default:
        return true;
    }
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter requests">
          {FILTERS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={filter === option}
              onClick={() => setFilter(option)}
              className={cn(
                "rounded border px-2 py-1 text-[11.5px] capitalize transition-colors",
                filter === option
                  ? "border-info/50 bg-info-dim font-semibold text-info"
                  : "border-line bg-panel text-muted hover:text-ink",
              )}
            >
              {option}
            </button>
          ))}
        </div>

        <button
          type="button"
          className="btn btn-primary"
          disabled={!session || !can(Permission.createRequest)}
          onClick={() => setShowForm((value) => !value)}
          title={session ? undefined : "Sign in to raise a request"}
        >
          {showForm ? <X size={13} aria-hidden="true" /> : <Plus size={13} aria-hidden="true" />}
          {showForm ? "Cancel" : "New request"}
        </button>
      </div>

      {showForm ? (
        <CreateRequestForm
          skus={skus?.skus ?? []}
          sites={sites?.sites ?? []}
          defaultSection={session?.operator.section ?? "operations"}
          onDone={() => {
            setShowForm(false);
            void queryClient.invalidateQueries();
          }}
        />
      ) : null}

      <section className="panel" aria-label="Resource requests">
        <div className="panel-head">
          <h2 className="panel-title">Requests</h2>
          <span className="text-[10px] text-faint">
            {isLoading ? "loading…" : `${requests.length} shown`}
          </span>
        </div>
        <RequestsTable requests={requests} viewRole={viewRole} caption="All resource requests" />
      </section>
    </div>
  );
}

function CreateRequestForm({
  skus,
  sites,
  defaultSection,
  onDone,
}: {
  skus: Array<{ id: string; code: string; name: string; unit: string }>;
  sites: Array<{ id: string; name: string; equity_priority: number }>;
  defaultSection: string;
  onDone: () => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      quantity: 10,
      priority: "priority",
      requesting_section: (["command", "operations", "planning", "logistics"].includes(
        defaultSection,
      )
        ? defaultSection
        : "operations") as FormValues["requesting_section"],
    },
  });

  const create = useMutation({
    mutationFn: (values: FormValues) =>
      api.createRequest({
        sku_id: values.sku_id,
        quantity: Number(values.quantity),
        priority: values.priority,
        requesting_section: values.requesting_section,
        destination_site_id: values.destination_site_id,
        justification: values.justification,
      }),
    onSuccess: onDone,
    onError: (cause) =>
      setServerError(cause instanceof ApiError ? cause.message : "Could not create the request."),
  });

  return (
    <form
      className="panel p-3"
      onSubmit={handleSubmit((values) => {
        setServerError(null);
        create.mutate(values);
      })}
    >
      <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
        New resource request
      </h2>

      <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
        <div>
          <label className="label" htmlFor="sku_id">
            Resource
          </label>
          <select id="sku_id" className="field" {...register("sku_id")}>
            <option value="">Select…</option>
            {skus.map((sku) => (
              <option key={sku.id} value={sku.id}>
                {sku.name} ({sku.code})
              </option>
            ))}
          </select>
          <FieldError message={errors.sku_id?.message} />
        </div>

        <div>
          <label className="label" htmlFor="quantity">
            Quantity
          </label>
          <input id="quantity" type="number" min={1} className="field" {...register("quantity")} />
          <FieldError message={errors.quantity?.message} />
        </div>

        <div>
          <label className="label" htmlFor="priority">
            Priority
          </label>
          <select id="priority" className="field" {...register("priority")}>
            <option value="routine">Routine — replenishment</option>
            <option value="priority">Priority — degradation within 24h</option>
            <option value="immediate">Immediate — life safety this period</option>
          </select>
          <FieldError message={errors.priority?.message} />
        </div>

        <div>
          <label className="label" htmlFor="destination_site_id">
            Destination
          </label>
          <select id="destination_site_id" className="field" {...register("destination_site_id")}>
            <option value="">Select…</option>
            {sites.map((site) => (
              <option key={site.id} value={site.id}>
                {site.name} (equity {site.equity_priority})
              </option>
            ))}
          </select>
          <FieldError message={errors.destination_site_id?.message} />
        </div>

        <div>
          <label className="label" htmlFor="requesting_section">
            Requesting section
          </label>
          <select id="requesting_section" className="field" {...register("requesting_section")}>
            <option value="operations">Operations</option>
            <option value="logistics">Logistics</option>
            <option value="planning">Planning</option>
            <option value="command">Command</option>
          </select>
          <FieldError message={errors.requesting_section?.message} />
        </div>
      </div>

      <div className="mt-2.5">
        <label className="label" htmlFor="justification">
          Justification
        </label>
        <textarea
          id="justification"
          className="field min-h-[3.5rem] resize-y"
          placeholder="What is the need, and what happens if it is not met this operational period?"
          {...register("justification")}
        />
        <FieldError message={errors.justification?.message} />
      </div>

      {serverError ? (
        <p
          role="alert"
          className="mt-2 flex items-center gap-1.5 rounded border border-immediate/40 bg-immediate-dim p-2 text-[12px] text-immediate"
        >
          <CircleAlert size={13} aria-hidden="true" />
          {serverError}
        </p>
      ) : null}

      <div className="mt-3 flex gap-2">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={isSubmitting || create.isPending}
        >
          {create.isPending ? (
            <Loader2 size={13} className="animate-spin" aria-hidden="true" />
          ) : (
            <Plus size={13} aria-hidden="true" />
          )}
          Submit request
        </button>
        <p className="self-center text-[10.5px] text-faint">
          Submitting logs the request and appends to the audit trail. It does not move stock.
        </p>
      </div>
    </form>
  );
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1 text-[11px] text-immediate">
      {message}
    </p>
  );
}
