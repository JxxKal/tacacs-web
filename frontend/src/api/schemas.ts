/** Zod schemas mirroring the Pydantic responses in the backend. */

import { z } from "zod";

export const MeSchema = z.object({
  username: z.string(),
  role: z.string(),
  auth_method: z.string(),
});
export type Me = z.infer<typeof MeSchema>;

export const DeviceGroupSchema = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullable(),
  created_at: z.string(),
});
export type DeviceGroup = z.infer<typeof DeviceGroupSchema>;
export const DeviceGroupListSchema = z.array(DeviceGroupSchema);
