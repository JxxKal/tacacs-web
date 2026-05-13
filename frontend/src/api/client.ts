/**
 * Fetch wrapper for the tacacs-web backend.
 *
 * Cookies (the HttpOnly session cookie set by `/login/local`) are sent
 * automatically because we use `credentials: "include"`. A 401 anywhere
 * during a normal navigation means the session has expired or never
 * existed; the router-level `RequireSession` guard handles redirection.
 */

import { z } from "zod";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | undefined;

  constructor(status: number, detail: string | undefined, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const init: RequestInit = {
    method: options.method ?? "GET",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    signal: options.signal,
  };
  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }
  return fetch(path, init);
}

async function parseErrorBody(response: Response): Promise<string | undefined> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return JSON.stringify(body.detail);
  } catch {
    // not JSON
  }
  return undefined;
}

/**
 * Issue a request and parse the JSON body against a Zod schema.
 *
 * Errors:
 * - HTTP non-2xx -> ApiError (carries .status + .detail from the body)
 * - Body shape mismatch -> Error (Zod thrown as-is)
 */
export async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  const response = await rawRequest(path, options);
  if (!response.ok) {
    const detail = await parseErrorBody(response);
    throw new ApiError(response.status, detail, `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const raw = (await response.json()) as unknown;
  return schema.parse(raw);
}

/** Request without a response body (e.g. logout). */
export async function apiVoid(path: string, options: RequestOptions = {}): Promise<void> {
  const response = await rawRequest(path, options);
  if (!response.ok) {
    const detail = await parseErrorBody(response);
    throw new ApiError(response.status, detail, `${response.status} ${response.statusText}`);
  }
}
