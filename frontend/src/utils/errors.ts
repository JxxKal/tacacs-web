import { ApiError } from "@/api/client";

/** Distill anything thrown by a mutation into a user-friendly string. */
export function errorToMessage(err: unknown): string {
  if (err instanceof ApiError && err.detail) return err.detail;
  if (err instanceof Error) return err.message;
  return String(err);
}
