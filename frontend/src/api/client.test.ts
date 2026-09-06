// frontend/src/api/client.test.ts

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./client";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  fetchMock.mockReset();
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("api client", () => {
  it("prefixes /api and parses JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { id: "abc" }));

    const result = await api<{ id: string }>("/users/me");

    expect(result).toEqual({ id: "abc" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/users/me");
  });

  it("sends the double-submit CSRF header on unsafe methods", async () => {
    document.cookie = "csrf_token=tok-123";
    fetchMock.mockResolvedValue(jsonResponse(200, {}));

    await api("/cashout/submissions", { method: "POST" });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Headers).get("x-csrf-token")).toBe("tok-123");
  });

  it("does not send a CSRF header on GET", async () => {
    document.cookie = "csrf_token=tok-123";
    fetchMock.mockResolvedValue(jsonResponse(200, {}));

    await api("/cashout/submissions");

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Headers).get("x-csrf-token")).toBeNull();
  });

  it("maps the error contract to ApiError", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, {
        kind: "CONFLICT",
        code: "EMAIL_TAKEN",
        ctx: {},
      }),
    );

    const failure = api("/users", {
      method: "POST",
      json: { email: "taken@test.com", fullName: "Taken User" },
    });

    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await failure.catch((error: ApiError) => {
      expect(error.status).toBe(409);
      expect(error.kind).toBe("CONFLICT");
      expect(error.code).toBe("EMAIL_TAKEN");
      expect(error.ctx).toEqual({});
      expect(error.message).toBe("This email is already in use.");
    });
  });

  it("captures the Retry-After header on rate-limited responses", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          kind: "TOO_MANY_REQUESTS",
          code: "RATE_LIMITED",
          ctx: { retryAfterSeconds: 120 },
        }),
        {
          status: 429,
          headers: {
            "Content-Type": "application/json",
            "Retry-After": "120",
          },
        },
      ),
    );

    await expect(
      api("/auth/login/start", { method: "POST" }),
    ).rejects.toMatchObject({
      status: 429,
      code: "RATE_LIMITED",
      retryAfterSeconds: 120,
      ctx: { retryAfterSeconds: 120 },
      message: "Too many attempts. Try again in 120 seconds.",
    });
  });

  it("leaves retryAfterSeconds null when the header is absent", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(429, {
        kind: "TOO_MANY_REQUESTS",
        code: "RATE_LIMITED",
        ctx: {},
      }),
    );

    await expect(
      api("/auth/login/start", { method: "POST" }),
    ).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: null,
    });
  });

  it("falls back to a generic error for non-JSON failures", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html>Bad gateway</html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      }),
    );

    await expect(api("/users/me")).rejects.toMatchObject({
      status: 502,
      code: "INTERNAL",
    });
  });

  it("builds field feedback from validation codes and context", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        kind: "VALIDATION",
        code: "VALIDATION_FAILED",
        ctx: {},
        issues: [
          {
            code: "greater_than_equal",
            path: ["items", 0, "amount"],
            ctx: { ge: 0 },
          },
        ],
      }),
    );

    const failure = api("/cashout/submissions");
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await failure.catch((error: ApiError) => {
      expect(error.messageFor("amount")).toBe("Must be at least 0.");
      expect(error.messageFor("missing")).toBeUndefined();
    });
  });

  it("does not use server-supplied wording", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(500, {
        kind: "INTERNAL",
        code: "INTERNAL",
        ctx: {},
        message: "private diagnostic",
      }),
    );

    await expect(api("/users/me")).rejects.toMatchObject({
      message: "Something went wrong.",
    });
  });

  it("returns undefined for 204 responses", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(
      api<void>("/auth/logout", { method: "POST" }),
    ).resolves.toBeUndefined();
  });
});
