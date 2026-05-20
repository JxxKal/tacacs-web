import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const EntrySchema = z.object({
  id: z.number(),
  ts: z.string(),
  nas_ip: z.string().nullable(),
  username: z.string().nullable(),
  port: z.string().nullable(),
  nac_ip: z.string().nullable(),
  action: z.string(),
  service: z.string().nullable(),
  cmd: z.string().nullable(),
  priv_lvl: z.number().nullable(),
  elapsed_seconds: z.number().nullable(),
  task_id: z.string().nullable(),
  device_id: z.number().nullable(),
  raw_av_pairs: z.record(z.string(), z.string()),
});

const PageSchema = z.object({
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  entries: z.array(EntrySchema),
});

export type AccountingEntry = z.infer<typeof EntrySchema>;
export type AccountingPage = z.infer<typeof PageSchema>;

export interface AccountingFilter {
  limit?: number;
  offset?: number;
  action?: string | null;
  username?: string | null;
  nas_ip?: string | null;
  task_id?: string | null;
  cmd?: string | null;
  since?: string | null;
  until?: string | null;
}

function buildQuery(filter: AccountingFilter): string {
  const params = new URLSearchParams();
  const set = (k: string, v: string | number | undefined | null) => {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  };
  set("limit", filter.limit ?? 100);
  set("offset", filter.offset ?? 0);
  set("action", filter.action);
  set("username", filter.username);
  set("nas_ip", filter.nas_ip);
  set("task_id", filter.task_id);
  set("cmd", filter.cmd);
  set("since", filter.since);
  set("until", filter.until);
  const q = params.toString();
  return q ? `?${q}` : "";
}

export function useAccounting(filter: AccountingFilter) {
  return useQuery({
    queryKey: ["accounting", filter] as const,
    queryFn: ({ signal }) =>
      apiRequest(`/api/v1/accounting${buildQuery(filter)}`, PageSchema, { signal }),
    placeholderData: (prev) => prev,
  });
}
