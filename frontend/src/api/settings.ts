import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const LdapSettingsSchema = z.object({ url: z.string().nullable() });
const WebSettingsSchema = z.object({ base_url: z.string().nullable() });

export type LdapSettings = z.infer<typeof LdapSettingsSchema>;
export type WebSettings = z.infer<typeof WebSettingsSchema>;

const LDAP_KEY = ["settings", "ldap"] as const;
const WEB_KEY = ["settings", "web"] as const;

export function useLdapSettings() {
  return useQuery({
    queryKey: LDAP_KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/settings/ldap", LdapSettingsSchema, { signal }),
  });
}

export function useUpdateLdapSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (url: string) =>
      apiRequest("/api/v1/settings/ldap", LdapSettingsSchema, {
        method: "PUT",
        body: { url },
      }),
    onSuccess: (data) => qc.setQueryData(LDAP_KEY, data),
  });
}

export function useWebSettings() {
  return useQuery({
    queryKey: WEB_KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/settings/web", WebSettingsSchema, { signal }),
  });
}

export function useUpdateWebSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (base_url: string) =>
      apiRequest("/api/v1/settings/web", WebSettingsSchema, {
        method: "PUT",
        body: { base_url },
      }),
    onSuccess: (data) => qc.setQueryData(WEB_KEY, data),
  });
}
