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
        message: "This email is already in use.",
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
      expect(error.message).toBe("This email is already in use.");
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

  it("returns undefined for 204 responses", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(
      api<void>("/auth/logout", { method: "POST" }),
    ).resolves.toBeUndefined();
  });
});
