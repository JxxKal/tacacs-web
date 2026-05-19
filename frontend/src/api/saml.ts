import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

export const SamlRoleSchema = z.enum(["admin", "operator", "viewer"]);
export type SamlRole = z.infer<typeof SamlRoleSchema>;

export const RoleMappingSchema = z.object({
  ad_group: z.string(),
  role: SamlRoleSchema,
});
export type RoleMapping = z.infer<typeof RoleMappingSchema>;

const SamlStatusSchema = z.object({
  configured: z.boolean(),
  sp_entity_id: z.string().nullable(),
  sp_acs_url: z.string().nullable(),
  sp_has_keypair: z.boolean(),
  idp_entity_id: z.string().nullable(),
  idp_sso_url: z.string().nullable(),
  idp_cert_present: z.boolean(),
  group_attribute: z.string(),
  role_mappings: z.array(RoleMappingSchema),
});
export type SamlStatus = z.infer<typeof SamlStatusSchema>;

const KEY = ["settings", "saml"] as const;

export function useSamlStatus() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/settings/saml", SamlStatusSchema, { signal }),
  });
}

export function useImportIdpMetadata() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (xml: string) =>
      apiRequest("/api/v1/settings/saml/idp-metadata", SamlStatusSchema, {
        method: "PUT",
        body: { xml },
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

export function useUpdateSamlMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { group_attribute: string; role_mappings: RoleMapping[] }) =>
      apiRequest("/api/v1/settings/saml/mapping", SamlStatusSchema, {
        method: "PUT",
        body: input,
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

export function useRegenerateSpKeypair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (common_name: string | null) =>
      apiRequest("/api/v1/settings/saml/sp-keypair", SamlStatusSchema, {
        method: "POST",
        body: { common_name },
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}
