// frontend/src/api/client.ts

import type { ErrorResponse, ValidationIssue } from "./types";

/** A backend error response (`{ kind, code, message, issues }`). */
export class ApiError extends Error {
  readonly status: number;
  readonly kind: ErrorResponse["kind"];
  readonly code: ErrorResponse["code"];
  readonly issues: ValidationIssue[];

  constructor(status: number, body: ErrorResponse) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.kind = body.kind;
    this.code = body.code;
    this.issues = body.issues ?? [];
  }

  /** The validation message for a field, if the backend flagged one. */
  messageFor(field: string): string | undefined {
    return this.issues.find((issue) => issue.path.at(-1) === field)?.message;
  }
}

const FALLBACK_BODY: ErrorResponse = {
  kind: "INTERNAL",
  code: "INTERNAL",
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
    );
  }
  return data as T;
}
