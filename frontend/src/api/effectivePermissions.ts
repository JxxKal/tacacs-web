import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const CandidateSchema = z.object({
  authorization_id: z.number(),
  principal_user_id: z.number().nullable(),
  principal_ad_group_id: z.number().nullable(),
  privilege_profile_id: z.number(),
  tacacs_priv_lvl: z.number().int(),
});

const EntrySchema = z.object({
  device_group_id: z.number(),
  device_group_name: z.string(),
  winning: CandidateSchema,
  overridden: z.array(CandidateSchema),
});

const ListSchema = z.array(EntrySchema);

export type EffectivePermissionEntry = z.infer<typeof EntrySchema>;
export type EffectivePermissionCandidate = z.infer<typeof CandidateSchema>;

export function useEffectivePermissions(userId: number | null) {
  return useQuery({
    queryKey: ["effective-permissions", userId] as const,
    queryFn: ({ signal }) =>
      apiRequest(`/api/v1/users/${userId}/effective-permissions`, ListSchema, {
        signal,
      }),
    enabled: userId !== null,
  });
}

const DeviceSchema = z.object({
  id: z.number(),
  name: z.string(),
  ip_or_cidr: z.string(),
});

const MyAccessGroupSchema = z.object({
  device_group_id: z.number(),
  device_group_name: z.string(),
  tacacs_priv_lvl: z.number().int(),
  privilege_profile_name: z.string(),
  via_ad_group_name: z.string().nullable(),
  devices: z.array(DeviceSchema),
  device_count: z.number().int(),
});

const MyAccessSchema = z.object({
  tacacs_username: z.string().nullable(),
  display_name: z.string().nullable(),
  groups: z.array(MyAccessGroupSchema),
});

export type MyAccessGroup = z.infer<typeof MyAccessGroupSchema>;
export type MyAccess = z.infer<typeof MyAccessSchema>;

export function useMyAccess() {
  return useQuery({
    queryKey: ["me", "access"] as const,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/me/access", MyAccessSchema, { signal }),
  });
}
