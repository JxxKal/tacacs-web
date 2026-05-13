import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "./client";
import { ADGroupListSchema, UserListSchema, type ADGroup, type User } from "./schemas";

export function useUsers() {
  return useQuery({
    queryKey: ["users"] as const,
    queryFn: ({ signal }) => apiRequest("/api/v1/users", UserListSchema, { signal }),
  });
}

export function useADGroups() {
  return useQuery({
    queryKey: ["ad-groups"] as const,
    queryFn: ({ signal }) => apiRequest("/api/v1/ad-groups", ADGroupListSchema, { signal }),
  });
}

export type { ADGroup, User };
