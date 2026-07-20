// frontend/src/api/invitations.ts

import { api } from "./client";
import type { Invitation, InvitationCreateInput } from "./types";

/** Admin-only: registration requires a pending invitation for the email. */
export const invitationsApi = {
  list: () => api<Invitation[]>("/invitations"),
  create: (input: InvitationCreateInput) =>
    api<Invitation>("/invitations", { method: "POST", json: input }),
  delete: (id: string) => api<void>(`/invitations/${id}`, { method: "DELETE" }),
};

/** Central react-query keys so invalidation stays consistent. */
export const invitationKeys = {
  list: ["invitations", "list"] as const,
};
