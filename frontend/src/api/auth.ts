import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiRequest, apiVoid } from "./client";
import { MeSchema, type Me } from "./schemas";

const ME_QUERY_KEY = ["me"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: ({ signal }) => apiRequest("/me", MeSchema, { signal }),
    retry: (failureCount, error) => {
      // 401 just means "not logged in"; treat it as a terminal state
      // rather than retrying.
      if (error instanceof ApiError && error.status === 401) return false;
      return failureCount < 1;
    },
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      apiRequest("/login/local", MeSchema, {
        method: "POST",
        body: { username, password },
      }),
    onSuccess: (data: Me) => {
      queryClient.setQueryData(ME_QUERY_KEY, data);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiVoid("/logout", { method: "POST" }),
    onSettled: () => {
      queryClient.setQueryData(ME_QUERY_KEY, null);
      // Drop every other query so the next login doesn't see a stale
      // cache from the previous session.
      queryClient.removeQueries();
    },
  });
}
