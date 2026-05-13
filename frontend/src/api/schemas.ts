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

export const PrivilegeProfileSchema = z.object({
  id: z.number(),
  name: z.string(),
  tacacs_priv_lvl: z.number().int().min(0).max(15),
  permit_commands_regex: z.array(z.string()),
  deny_commands_regex: z.array(z.string()),
  extra_av_pairs: z.record(z.string(), z.string()),
  description: z.string().nullable(),
  created_at: z.string(),
});
export type PrivilegeProfile = z.infer<typeof PrivilegeProfileSchema>;
export const PrivilegeProfileListSchema = z.array(PrivilegeProfileSchema);

export const DeviceSchema = z.object({
  id: z.number(),
  name: z.string(),
  ip_or_cidr: z.string(),
  device_group_id: z.number(),
  has_current_secret: z.boolean(),
  has_previous_secret: z.boolean(),
  previous_retired_at: z.string().nullable(),
  description: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Device = z.infer<typeof DeviceSchema>;
export const DeviceListSchema = z.array(DeviceSchema);

export const AuthorizationSchema = z.object({
  id: z.number(),
  principal_user_id: z.number().nullable(),
  principal_ad_group_id: z.number().nullable(),
  device_group_id: z.number(),
  privilege_profile_id: z.number(),
  created_at: z.string(),
});
export type Authorization = z.infer<typeof AuthorizationSchema>;
export const AuthorizationListSchema = z.array(AuthorizationSchema);

export const UserSchema = z.object({
  id: z.number(),
  sam_account_name: z.string(),
  distinguished_name: z.string(),
  display_name: z.string().nullable(),
  upn: z.string().nullable(),
  enabled: z.boolean(),
  last_seen_in_sync_at: z.string().nullable(),
});
export type User = z.infer<typeof UserSchema>;
export const UserListSchema = z.array(UserSchema);

export const ADGroupSchema = z.object({
  id: z.number(),
  sid: z.string(),
  distinguished_name: z.string(),
  name: z.string().nullable(),
  last_seen_in_sync_at: z.string().nullable(),
});
export type ADGroup = z.infer<typeof ADGroupSchema>;
export const ADGroupListSchema = z.array(ADGroupSchema);
