import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const SetupStepSchema = z.object({
  key: z.string(),
  done: z.boolean(),
  required: z.boolean(),
  detail: z.string().nullable(),
});

const SetupStatusSchema = z.object({
  completed: z.boolean(),
  completed_by: z.string().nullable(),
  can_complete: z.boolean(),
  steps: z.array(SetupStepSchema),
});

export type SetupStep = z.infer<typeof SetupStepSchema>;
export type SetupStatus = z.infer<typeof SetupStatusSchema>;

const KEY = ["setup", "status"] as const;

export function useSetupStatus() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/setup", SetupStatusSchema, { signal }),
  });
}

export function useCompleteSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest("/api/v1/setup/complete", SetupStatusSchema, {
        method: "POST",
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

export function useReopenSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest("/api/v1/setup/reopen", SetupStatusSchema, {
        method: "POST",
      }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}
