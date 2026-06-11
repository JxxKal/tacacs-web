import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest, apiVoid } from "./client";
import { DeviceListSchema, DeviceSchema, type Device } from "./schemas";

const LIST_KEY = ["devices"] as const;

export interface DeviceCreateInput {
  name: string;
  ip_or_cidr: string;
  device_group_id: number;
  current_secret: string | null;
  description: string | null;
}

export interface DeviceUpdateInput {
  name?: string;
  ip_or_cidr?: string;
  device_group_id?: number;
  description?: string | null;
  current_secret?: string | null;
}

export function useDevices() {
  return useQuery({
    queryKey: LIST_KEY,
    queryFn: ({ signal }) => apiRequest("/api/v1/devices", DeviceListSchema, { signal }),
  });
}

export function useCreateDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: DeviceCreateInput) =>
      apiRequest("/api/v1/devices", DeviceSchema, { method: "POST", body: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useUpdateDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: DeviceUpdateInput & { id: number }) =>
      apiRequest(`/api/v1/devices/${id}`, DeviceSchema, { method: "PATCH", body: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useDeleteDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiVoid(`/api/v1/devices/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useRotateDeviceSecret() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, new_secret }: { id: number; new_secret: string }) =>
      apiRequest(`/api/v1/devices/${id}/rotate-secret`, DeviceSchema, {
        method: "POST",
        body: { new_secret },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useRetirePreviousSecret() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/api/v1/devices/${id}/retire-previous`, DeviceSchema, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export type { Device };
