// frontend/src/api/client.ts

import type { ErrorBody, ErrorDetail } from "./types";

/** A backend error response (`{ error, code, message, errors }`). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorBody["code"];
  readonly details: ErrorDetail[];

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.errors ?? [];
  }

  /** The validation detail for a field, if the backend flagged one. */
  detailFor(field: string): string | undefined {
    return this.details.find((d) => d.path.at(-1) === field)?.detail;
  }
}

const FALLBACK_BODY: ErrorBody = {
  error: "Server Error",
  code: "SERVER_ERROR",
  message: "Something went wrong.",
};

function readCookie(name: string): string | null {
  const match = document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** JSON body; serialized and content-typed automatically. */
  json?: unknown;
  /** Raw body (e.g. FormData for uploads); mutually exclusive with `json`. */
  body?: BodyInit;
}

/**
 * Fetch wrapper for the backend API: same-origin cookies, the double-submit
 * CSRF header on unsafe methods, and the error contract mapped to `ApiError`.
 */
export async function api<T>(
  path: string,
  { method = "GET", json, body }: RequestOptions = {},
): Promise<T> {
  const headers = new Headers();
  if (json !== undefined) headers.set("Content-Type", "application/json");
  if (method !== "GET") {
    headers.set("x-csrf-token", readCookie("csrf_token") ?? "");
  }

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: json !== undefined ? JSON.stringify(json) : body,
  });

  if (response.status === 204) return undefined as T;

  const isJson = (response.headers.get("content-type") ?? "").includes(
    "application/json",
  );
  const data: unknown = isJson ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      (data as ErrorBody | null) ?? FALLBACK_BODY,
    );
  }
  return data as T;
}
