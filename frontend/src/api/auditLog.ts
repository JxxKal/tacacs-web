import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const EntrySchema = z.object({
  id: z.number(),
  ts: z.string(),
  actor_id: z.number().nullable(),
  actor_username_snapshot: z.string(),
  actor_role: z.string(),
  auth_method: z.string(),
  action: z.string(),
  target_type: z.string().nullable(),
  target_id: z.number().nullable(),
  summary: z.string().nullable(),
  client_ip: z.string().nullable(),
  user_agent: z.string().nullable(),
});

const PageSchema = z.object({
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  entries: z.array(EntrySchema),
});

const ActionsSchema = z.object({
  actions: z.array(z.string()),
});

export type AuditEntry = z.infer<typeof EntrySchema>;
export type AuditPage = z.infer<typeof PageSchema>;

export interface AuditFilter {
  limit?: number;
  offset?: number;
  action?: string | null;
  username?: string | null;
  auth_method?: string | null;
  since?: string | null;
  until?: string | null;
}

function buildQuery(filter: AuditFilter): string {
  const params = new URLSearchParams();
  const set = (k: string, v: string | number | undefined | null) => {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  };
  set("limit", filter.limit ?? 100);
  set("offset", filter.offset ?? 0);
  set("action", filter.action);
  set("username", filter.username);
  set("auth_method", filter.auth_method);
  set("since", filter.since);
  set("until", filter.until);
  const q = params.toString();
  return q ? `?${q}` : "";
}

export function useAuditLog(filter: AuditFilter) {
  return useQuery({
    queryKey: ["audit-log", filter] as const,
    queryFn: ({ signal }) =>
      apiRequest(`/api/v1/audit-log${buildQuery(filter)}`, PageSchema, { signal }),
    placeholderData: (prev) => prev,
  });
}

export function useAuditLogActions() {
  return useQuery({
    queryKey: ["audit-log-actions"] as const,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/audit-log/actions", ActionsSchema, { signal }),
    staleTime: 5 * 60_000,
  });
}
