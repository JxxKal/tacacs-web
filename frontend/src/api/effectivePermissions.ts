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
