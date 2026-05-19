import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const LastSyncSchema = z.object({
  started_at: z.string(),
  finished_at: z.string().nullable(),
  users_seen: z.number(),
  users_inserted: z.number(),
  users_updated: z.number(),
  users_disabled: z.number(),
  groups_seen: z.number(),
  error: z.string().nullable(),
});

const StatusSchema = z.object({
  configured: z.boolean(),
  url: z.string().nullable(),
  bind_dn: z.string().nullable(),
  bind_password_set: z.boolean(),
  base_dns: z.array(z.string()),
  user_filter: z.string().nullable(),
  cadence_seconds: z.number(),
  enabled: z.boolean(),
  last_sync: LastSyncSchema.nullable(),
});

export type LdapSyncStatus = z.infer<typeof StatusSchema>;
export type LdapSyncLastRun = z.infer<typeof LastSyncSchema>;

export interface LdapSyncUpdate {
  bind_dn: string;
  bind_password: string | null;
  base_dns: string[];
  user_filter: string | null;
  cadence_seconds: number;
  enabled: boolean;
}

const KEY = ["settings", "ldap-sync"] as const;

export function useLdapSyncStatus() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/settings/ldap-sync", StatusSchema, { signal }),
  });
}

export function useUpdateLdapSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LdapSyncUpdate) =>
      apiRequest("/api/v1/settings/ldap-sync", StatusSchema, {
        method: "PUT",
        body: payload,
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

const TestResponse = z.object({ status: z.string() });

export function useTestLdapConnection() {
  return useMutation({
    mutationFn: (payload: {
      url: string | null;
      bind_dn: string | null;
      bind_password: string | null;
    }) =>
      apiRequest("/api/v1/settings/ldap-sync/test", TestResponse, {
        method: "POST",
        body: payload,
      }),
  });
}

export function useRunLdapSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest("/api/v1/settings/ldap-sync/run", StatusSchema, {
        method: "POST",
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}
