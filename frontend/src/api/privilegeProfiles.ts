import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest, apiVoid } from "./client";
import {
  PrivilegeProfileListSchema,
  PrivilegeProfileSchema,
  type PrivilegeProfile,
} from "./schemas";

const LIST_KEY = ["privilege-profiles"] as const;

export interface PrivilegeProfileInput {
  name: string;
  tacacs_priv_lvl: number;
  permit_commands_regex: string[];
  deny_commands_regex: string[];
  extra_av_pairs: Record<string, string>;
  description: string | null;
}

export function usePrivilegeProfiles() {
  return useQuery({
    queryKey: LIST_KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/privilege-profiles", PrivilegeProfileListSchema, { signal }),
  });
}

export function useCreatePrivilegeProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: PrivilegeProfileInput) =>
      apiRequest("/api/v1/privilege-profiles", PrivilegeProfileSchema, {
        method: "POST",
        body: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useUpdatePrivilegeProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: PrivilegeProfileInput & { id: number }) =>
      apiRequest(`/api/v1/privilege-profiles/${id}`, PrivilegeProfileSchema, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useDeletePrivilegeProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiVoid(`/api/v1/privilege-profiles/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export type { PrivilegeProfile };
