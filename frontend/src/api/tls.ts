import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const CertInfoSchema = z.object({
  subject_cn: z.string().nullable(),
  issuer_cn: z.string().nullable(),
  san_dns: z.array(z.string()),
  not_before: z.string(),
  not_after: z.string(),
  fingerprint_sha256: z.string(),
  is_self_signed: z.boolean(),
  source: z.string(),
});

const TlsStatusSchema = z.object({
  has_cert: z.boolean(),
  info: CertInfoSchema.nullable(),
});

export type CertInfo = z.infer<typeof CertInfoSchema>;
export type TlsStatus = z.infer<typeof TlsStatusSchema>;

const KEY = ["settings", "tls"] as const;

export function useTlsStatus() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/settings/tls", TlsStatusSchema, { signal }),
  });
}

export function useUploadTls() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ cert_pem, key_pem }: { cert_pem: string; key_pem: string }) =>
      apiRequest("/api/v1/settings/tls/upload", TlsStatusSchema, {
        method: "POST",
        body: { cert_pem, key_pem },
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

export function useRegenerateTls() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ common_name, days }: { common_name: string; days: number }) =>
      apiRequest("/api/v1/settings/tls/regenerate-self-signed", TlsStatusSchema, {
        method: "POST",
        body: { common_name, days },
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}
