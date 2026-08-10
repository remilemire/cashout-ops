// frontend/src/features/admin/AdminUsersPage.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Crown,
  ShieldMinus,
  ShieldPlus,
  Trash2,
  UserPlus,
  UsersRound,
} from "lucide-react";
import { useState, type SyntheticEvent } from "react";

import { ApiError } from "@/api/client";
import type { User, UserRole } from "@/api/types";
import { userKeys, usersApi } from "@/api/users";
import { ME_KEY, useAuth } from "@/auth/useAuth";
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

type UserAction = {
  user: User;
  action: "promote" | "demote" | "delete" | "transfer";
};

const ROLE_BADGES = {
  staff: { label: "Staff", tone: "neutral" },
  admin: { label: "Admin", tone: "accent" },
  owner: { label: "Owner", tone: "warning" },
} as const satisfies Record<UserRole, unknown>;

const ACTION_DIALOGS: Record<
  UserAction["action"],
  {
    title: string;
    confirmLabel: string;
    confirmTone: "primary" | "danger";
    body: (user: User) => string;
  }
> = {
  promote: {
    title: "Promote to admin",
    confirmLabel: "Promote",
    confirmTone: "primary",
    body: (user) => `${user.fullName} will gain full admin access.`,
  },
  demote: {
    title: "Demote to staff",
    confirmLabel: "Demote",
    confirmTone: "primary",
    body: (user) => `${user.fullName} will lose admin access and become staff.`,
  },
  delete: {
    title: "Delete user",
    confirmLabel: "Delete",
    confirmTone: "danger",
    body: (user) =>
      `${user.fullName}'s account will be permanently deleted. This can't be undone.`,
  },
  transfer: {
    title: "Transfer ownership",
    confirmLabel: "Transfer",
    confirmTone: "primary",
    body: (user) =>
      `${user.fullName} will become the owner, and you will become a regular admin.`,
  },
};

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [userAction, setUserAction] = useState<UserAction | null>(null);

  const usersQuery = useQuery({
    queryKey: userKeys.list,
    queryFn: usersApi.list,
  });

  const createUser = useMutation({
    mutationFn: usersApi.create,
    onSuccess: async () => {
      setFullName("");
      setEmail("");
      await queryClient.invalidateQueries({ queryKey: userKeys.list });
    },
  });
  const promoteUser = useMutation({
    mutationFn: usersApi.promote,
    onSuccess: async () => {
      setUserAction(null);
      await queryClient.invalidateQueries({ queryKey: userKeys.list });
    },
  });
  const demoteUser = useMutation({
    mutationFn: usersApi.demote,
    onSuccess: async () => {
      setUserAction(null);
      await queryClient.invalidateQueries({ queryKey: userKeys.list });
    },
  });
  const deleteUser = useMutation({
    mutationFn: usersApi.remove,
    onSuccess: async () => {
      setUserAction(null);
      await queryClient.invalidateQueries({ queryKey: userKeys.list });
    },
  });
  const transferOwnership = useMutation({
    mutationFn: usersApi.transferOwnership,
    onSuccess: async () => {
      setUserAction(null);
      // The caller's own role changed too (owner → admin), so refresh the
      // session user alongside the list to update the nav without a reload.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: userKeys.list }),
        queryClient.invalidateQueries({ queryKey: ME_KEY }),
      ]);
    },
  });

  const onCreate = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = fullName.trim();
    const trimmedEmail = email.trim();
    if (trimmedName && trimmedEmail) {
      createUser.mutate({ email: trimmedEmail, fullName: trimmedName });
    }
  };

  const createError = createUser.error;
  const fullNameError =
    createError instanceof ApiError
      ? createError.messageFor("fullName")
      : undefined;
  const emailError =
    createError instanceof ApiError
      ? createError.messageFor("email")
      : undefined;
  const hasFieldError = fullNameError !== undefined || emailError !== undefined;

  const users = usersQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Users"
        subtitle="Create staff accounts and manage access."
      />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Add user</h2>
        <Card className="space-y-4">
          <form
            onSubmit={onCreate}
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
          >
            <div className="min-w-0 flex-1">
              <TextField
                label="Full name"
                required
                placeholder="Jane Smith"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                error={fullNameError}
              />
            </div>
            <div className="min-w-0 flex-1">
              <TextField
                label="Email"
                type="email"
                required
                placeholder="name@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                error={emailError}
              />
            </div>
            <Button type="submit" loading={createUser.isPending}>
              <UserPlus className="size-4" />
              Add user
            </Button>
          </form>
          <ErrorBanner error={hasFieldError ? null : createError} />
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Accounts</h2>
        <ErrorBanner error={usersQuery.error} />
        <ErrorBanner error={promoteUser.error} />
        <ErrorBanner error={demoteUser.error} />
        <ErrorBanner error={deleteUser.error} />
        <ErrorBanner error={transferOwnership.error} />

        {usersQuery.isLoading ? (
          <SkeletonList count={3} />
        ) : users.length === 0 ? (
          <EmptyState
            icon={<UsersRound className="size-8" strokeWidth={1.5} />}
            title="No users yet"
            hint="Add a user above to create the first account."
          />
        ) : (
          <Card padded={false} className="overflow-x-auto">
            <table className="w-full min-w-120 text-sm">
              <thead>
                <tr className="border-line text-ink-muted border-b text-left text-xs">
                  <th className="px-4 py-2.5 font-medium">User</th>
                  <th className="px-4 py-2.5 font-medium">Role</th>
                  <th className="px-4 py-2.5 font-medium">Joined</th>
                  <th className="px-4 py-2.5 font-medium">
                    <span className="sr-only">Actions</span>
                  </th>
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
                      <Badge tone={ROLE_BADGES[user.role].tone}>
                        {ROLE_BADGES[user.role].label}
                      </Badge>
                    </td>
                    <td className="text-ink-muted px-4 py-3">
                      {formatDateTime(user.createdAt)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {/* The owner is untouchable, and self-targeted actions
                          stay hidden (the only ones left here would be
                          self-demote and self-delete). */}
                      {user.role !== "owner" && user.id !== currentUser?.id && (
                        <span className="inline-flex items-center gap-1">
                          {user.role === "admin" ? (
                            <>
                              {currentUser?.role === "owner" && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={`Transfer ownership to ${user.fullName}`}
                                  onClick={() =>
                                    setUserAction({
                                      user,
                                      action: "transfer",
                                    })
                                  }
                                >
                                  <Crown className="text-warning size-4" />
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={`Demote ${user.fullName} to staff`}
                                onClick={() =>
                                  setUserAction({ user, action: "demote" })
                                }
                              >
                                <ShieldMinus className="size-4" />
                              </Button>
                            </>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`Promote ${user.fullName} to admin`}
                              onClick={() =>
                                setUserAction({ user, action: "promote" })
                              }
                            >
                              <ShieldPlus className="text-accent-strong size-4" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`Delete ${user.fullName}`}
                            onClick={() =>
                              setUserAction({ user, action: "delete" })
                            }
                          >
                            <Trash2 className="text-danger size-4" />
                          </Button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      <ConfirmDialog
        open={userAction !== null}
        onClose={() => setUserAction(null)}
        title={userAction ? ACTION_DIALOGS[userAction.action].title : ""}
        confirmLabel={
          userAction ? ACTION_DIALOGS[userAction.action].confirmLabel : ""
        }
        confirmTone={
          userAction ? ACTION_DIALOGS[userAction.action].confirmTone : "primary"
        }
        onConfirm={() => {
          if (!userAction) return;
          const { user, action } = userAction;
          if (action === "promote") promoteUser.mutate(user.id);
          else if (action === "demote") demoteUser.mutate(user.id);
          else if (action === "delete") deleteUser.mutate(user.id);
          else transferOwnership.mutate(user.id);
        }}
      >
        {userAction && ACTION_DIALOGS[userAction.action].body(userAction.user)}
      </ConfirmDialog>
    </div>
  );
}
