import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest } from "./client";

const HintsSchema = z.object({
  server_host: z.string().nullable(),
  tacacs_port: z.number(),
});

export type DeviceTemplateHints = z.infer<typeof HintsSchema>;

export function useDeviceTemplateHints() {
  return useQuery({
    queryKey: ["device-templates", "hints"],
    queryFn: ({ signal }) =>
      apiRequest("/api/v1/device-templates", HintsSchema, { signal }),
  });
}
