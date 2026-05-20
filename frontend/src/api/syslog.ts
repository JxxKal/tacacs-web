import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const StatusSchema = z.object({
  enabled: z.boolean(),
  host: z.string().nullable(),
  port: z.number(),
  protocol: z.enum(["tcp", "tls"]),
  facility: z.number(),
  app_name: z.string(),
  hostname: z.string(),
  tls_verify: z.boolean(),
  tls_server_name: z.string().nullable(),
  tls_ca_present: z.boolean(),
  tls_client_cert_present: z.boolean(),
  tls_client_key_present: z.boolean(),
  last_forwarded_id: z.number(),
  last_audit_id: z.number(),
  last_error: z.string().nullable(),
  last_error_at: z.string().nullable(),
});

export type SyslogStatus = z.infer<typeof StatusSchema>;

export interface SyslogUpdate {
  enabled: boolean;
  host: string;
  port: number;
  protocol: "tcp" | "tls";
  facility: number;
  app_name: string;
  hostname: string;
  tls_verify: boolean;
  tls_server_name: string | null;
  tls_ca_pem?: string | null;
  tls_client_cert_pem?: string | null;
  tls_client_key_pem?: string | null;
}

const KEY = ["settings", "syslog"] as const;

export function useSyslogStatus() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/settings/syslog", StatusSchema, { signal }),
  });
}

export function useUpdateSyslog() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: SyslogUpdate) =>
      apiRequest("/api/v1/settings/syslog", StatusSchema, {
        method: "PUT",
        body: input,
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

const TestResponse = z.object({ status: z.string() });

export function useTestSyslog() {
  return useMutation({
    mutationFn: () =>
      apiRequest("/api/v1/settings/syslog/test", TestResponse, {
        method: "POST",
      }),
  });
}
