// frontend/src/features/admin/AdminUsersPage.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailPlus, Trash2, UsersRound } from "lucide-react";
import { useState, type SyntheticEvent } from "react";

import { invitationKeys, invitationsApi } from "@/api/invitations";
import type { Invitation } from "@/api/types";
import { userKeys, usersApi } from "@/api/users";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SkeletonList,
  TextField,
} from "@/components/ui";
import { formatDateTime, initials } from "@/lib/format";

type InvitationStatus = "pending" | "accepted" | "expired";

function invitationStatus(invitation: Invitation): InvitationStatus {
  if (invitation.acceptedAt) return "accepted";
  if (new Date(invitation.expiresAt).getTime() < Date.now()) return "expired";
  return "pending";
}

function invitationDetail(invitation: Invitation): string {
  if (invitation.acceptedAt) {
    return `Accepted ${formatDateTime(invitation.acceptedAt)}`;
  }
  const verb =
    invitationStatus(invitation) === "expired" ? "Expired" : "Expires";
  return `${verb} ${formatDateTime(invitation.expiresAt)}`;
}

const INVITATION_BADGES: Record<
  InvitationStatus,
  { tone: "info" | "success" | "neutral"; label: string }
> = {
  pending: { tone: "info", label: "Pending" },
  accepted: { tone: "success", label: "Accepted" },
  expired: { tone: "neutral", label: "Expired" },
};

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [revoking, setRevoking] = useState<Invitation | null>(null);

  const usersQuery = useQuery({
    queryKey: userKeys.list,
    queryFn: usersApi.list,
  });
  const invitationsQuery = useQuery({
    queryKey: invitationKeys.list,
    queryFn: invitationsApi.list,
  });

  const createInvitation = useMutation({
    mutationFn: invitationsApi.create,
    onSuccess: async () => {
      setEmail("");
      await queryClient.invalidateQueries({ queryKey: invitationKeys.list });
    },
  });
  const deleteInvitation = useMutation({
    mutationFn: invitationsApi.delete,
    onSuccess: async () => {
      setRevoking(null);
      await queryClient.invalidateQueries({ queryKey: invitationKeys.list });
    },
  });

  const onInvite = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = email.trim();
    if (trimmed) createInvitation.mutate({ email: trimmed });
  };

  const users = usersQuery.data ?? [];
  const invitations = invitationsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Users"
        subtitle="Invite staff and manage their accounts."
      />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Invitations</h2>
        <Card className="space-y-4">
          <form
            onSubmit={onInvite}
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
          >
            <div className="min-w-0 flex-1">
              <TextField
                label="Invite by email"
                type="email"
                required
                placeholder="name@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <Button type="submit" loading={createInvitation.isPending}>
              <MailPlus className="size-4" />
              Invite
            </Button>
          </form>
          <ErrorBanner error={createInvitation.error} />
          <ErrorBanner error={deleteInvitation.error} />
          <ErrorBanner error={invitationsQuery.error} />

          {invitationsQuery.isLoading ? (
            <SkeletonList count={2} />
          ) : invitations.length === 0 ? (
            <EmptyState
              icon={<MailPlus className="size-8" strokeWidth={1.5} />}
              title="No invitations"
              hint="Only invited emails can register."
            />
          ) : (
            <ul className="divide-line divide-y">
              {invitations.map((invitation) => {
                const badge = INVITATION_BADGES[invitationStatus(invitation)];
                return (
                  <li
                    key={invitation.id}
                    className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {invitation.email}
                      </p>
                      <p className="text-ink-muted text-xs">
                        {invitationDetail(invitation)}
                      </p>
                    </div>
                    <Badge tone={badge.tone}>{badge.label}</Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Delete invitation for ${invitation.email}`}
                      onClick={() => setRevoking(invitation)}
                    >
                      <Trash2 className="text-danger size-4" />
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Accounts</h2>
        <ErrorBanner error={usersQuery.error} />

        {usersQuery.isLoading ? (
          <SkeletonList count={3} />
        ) : users.length === 0 ? (
          <EmptyState
            icon={<UsersRound className="size-8" strokeWidth={1.5} />}
            title="No users yet"
          />
        ) : (
          <Card padded={false} className="overflow-x-auto">
            <table className="w-full min-w-120 text-sm">
              <thead>
                <tr className="border-line text-ink-muted border-b text-left text-xs">
                  <th className="px-4 py-2.5 font-medium">User</th>
                  <th className="px-4 py-2.5 font-medium">Role</th>
                  <th className="px-4 py-2.5 font-medium">Joined</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr
                    key={user.id}
                    className="border-line border-b last:border-0"
                  >
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-2.5">
                        <span className="bg-accent/15 text-accent-strong grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold">
                          {initials(user.fullName)}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate font-medium">
                            {user.fullName}
                          </span>
                          <span className="text-ink-muted block truncate text-xs">
                            {user.email}
                          </span>
                        </span>
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={user.isAdmin ? "accent" : "neutral"}>
                        {user.isAdmin ? "Admin" : "Staff"}
                      </Badge>
                    </td>
                    <td className="text-ink-muted px-4 py-3">
                      {formatDateTime(user.createdAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      <ConfirmDialog
        open={revoking !== null}
        onClose={() => setRevoking(null)}
        title="Delete invitation"
        confirmLabel="Delete"
        confirmTone="danger"
        onConfirm={() => {
          if (revoking) deleteInvitation.mutate(revoking.id);
        }}
      >
        {revoking?.email} will no longer be able to register with this
        invitation.
      </ConfirmDialog>
    </div>
  );
}
