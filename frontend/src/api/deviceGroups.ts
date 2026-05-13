import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest, apiVoid } from "./client";
import { DeviceGroupListSchema, DeviceGroupSchema, type DeviceGroup } from "./schemas";

const LIST_KEY = ["device-groups"] as const;

export function useDeviceGroups() {
  return useQuery({
    queryKey: LIST_KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/device-groups", DeviceGroupListSchema, { signal }),
  });
}

export interface DeviceGroupInput {
  name: string;
  description: string | null;
}

export function useCreateDeviceGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: DeviceGroupInput) =>
      apiRequest("/api/v1/device-groups", DeviceGroupSchema, {
        method: "POST",
        body: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useUpdateDeviceGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: DeviceGroupInput & { id: number }) =>
      apiRequest(`/api/v1/device-groups/${id}`, DeviceGroupSchema, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useDeleteDeviceGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiVoid(`/api/v1/device-groups/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export type { DeviceGroup };
