import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest, apiVoid } from "./client";
import {
  AuthorizationListSchema,
  AuthorizationSchema,
  type Authorization,
} from "./schemas";

const LIST_KEY = ["authorizations"] as const;

export interface AuthorizationCreateInput {
  principal_user_id: number | null;
  principal_ad_group_id: number | null;
  device_group_id: number;
  privilege_profile_id: number;
}

export function useAuthorizations() {
  return useQuery({
    queryKey: LIST_KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/authorizations", AuthorizationListSchema, { signal }),
  });
}

export function useCreateAuthorization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: AuthorizationCreateInput) =>
      apiRequest("/api/v1/authorizations", AuthorizationSchema, {
        method: "POST",
        body: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useDeleteAuthorization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiVoid(`/api/v1/authorizations/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export type { Authorization };
