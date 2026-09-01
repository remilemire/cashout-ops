// frontend/src/api/client.ts

import type { ErrorResponse, ValidationIssue } from "./types";

/** A backend error response (`{ kind, code, message, issues }`). */
export class ApiError extends Error {
  readonly status: number;
  readonly kind: ErrorResponse["kind"];
  readonly code: ErrorResponse["code"];
  readonly issues: ValidationIssue[];
  /** Wait hint from a 429's `Retry-After` header, in whole seconds. */
  readonly retryAfterSeconds: number | null;

  constructor(
    status: number,
    body: ErrorResponse,
    retryAfterSeconds: number | null = null,
  ) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.kind = body.kind;
    this.code = body.code;
    this.issues = body.issues ?? [];
    this.retryAfterSeconds = retryAfterSeconds;
  }

  /** The validation message for a field, if the backend flagged one. */
  messageFor(field: string): string | undefined {
    return this.issues.find((issue) => issue.path.at(-1) === field)?.message;
  }
}

/**
 * Whether the failure says the resource no longer exists — deleted meanwhile
 * by another tab, another user, or an admin. Callers use it to retire dead
 * references (stop polling, refresh the page) instead of surfacing a retry.
 */
export function isNotFound(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 404;
}

const FALLBACK_BODY: ErrorResponse = {
  kind: "INTERNAL",
  code: "INTERNAL",
  message: "Something went wrong.",
};

/** The backend sends `Retry-After` as integer seconds; anything else is ignored. */
function parseRetryAfter(value: string | null): number | null {
  return value !== null && /^\d+$/.test(value) ? Number(value) : null;
}

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

  const request: RequestInit = {
    method,
    headers,
    credentials: "same-origin",
  };
  if (json !== undefined) request.body = JSON.stringify(json);
  else if (body !== undefined) request.body = body;

  const response = await fetch(`/api${path}`, request);

  if (response.status === 204) return undefined as T;

  const isJson = (response.headers.get("content-type") ?? "").includes(
    "application/json",
  );
  const data: unknown = isJson ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      (data as ErrorResponse | null) ?? FALLBACK_BODY,
      parseRetryAfter(response.headers.get("Retry-After")),
    );
  }
  return data as T;
}
