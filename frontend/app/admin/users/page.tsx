"use client";

import React, { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCurrentUser, getAdminUsers, updateUserRole, AdminUserItem, UserProfile } from "@/lib/api";

export default function AdminUsersPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [loadingUser, setLoadingUser] = useState(true);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [selectedRoles, setSelectedRoles] = useState<Record<string, "student" | "faculty" | "admin">>({});
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fetchUsers = useCallback(async (query: string = "") => {
    setLoadingUsers(true);
    setError(null);
    try {
      const res = await getAdminUsers(query);
      setUsers(res.users);
      setTotal(res.total);
      const rolesMap: Record<string, "student" | "faculty" | "admin"> = {};
      res.users.forEach((u) => {
        rolesMap[u.id] = u.role;
      });
      setSelectedRoles(rolesMap);
    } catch {
      setError("Failed to load users.");
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  useEffect(() => {
    async function checkAuthAndLoad() {
      try {
        const user = await getCurrentUser();
        if (!user || user.role !== "admin") {
          router.replace("/dashboard");
          return;
        }
        setCurrentUser(user);
        const res = await getAdminUsers("");
        setUsers(res.users);
        setTotal(res.total);
        const rolesMap: Record<string, "student" | "faculty" | "admin"> = {};
        res.users.forEach((u) => {
          rolesMap[u.id] = u.role;
        });
        setSelectedRoles(rolesMap);
      } catch {
        router.replace("/dashboard");
      } finally {
        setLoadingUser(false);
      }
    }
    checkAuthAndLoad();
  }, [router]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchUsers(search.trim());
  };

  const handleRoleChange = (userId: string, newRole: "student" | "faculty" | "admin") => {
    setSelectedRoles((prev) => ({
      ...prev,
      [userId]: newRole,
    }));
  };

  const handleSaveRole = async (user: AdminUserItem) => {
    const newRole = selectedRoles[user.id];
    if (!newRole || newRole === user.role) return;

    if (!confirm(`Are you sure you want to change ${user.username}'s role from ${user.role} to ${newRole}?`)) {
      return;
    }

    setSavingUserId(user.id);
    setError(null);
    setSuccess(null);

    const res = await updateUserRole(user.id, newRole);
    if (res.ok) {
      setSuccess(`Updated ${user.username}'s role to ${newRole}.`);
      setUsers((prev) =>
        prev.map((u) => (u.id === user.id ? { ...u, role: newRole } : u))
      );
    } else {
      setError(res.error || "Failed to update role.");
      // revert selection
      setSelectedRoles((prev) => ({
        ...prev,
        [user.id]: user.role,
      }));
    }
    setSavingUserId(null);
  };

  if (loadingUser) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center text-text-muted text-sm">
        Checking permissions...
      </div>
    );
  }

  if (!currentUser || currentUser.role !== "admin") {
    return null;
  }

  return (
    <div className="min-h-full flex flex-col bg-bg">
      <header className="w-full h-[56px] border-b border-border bg-surface">
        <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="font-serif text-[18px] font-semibold text-text tracking-tight hover:opacity-90"
            >
              Provenance
            </Link>
            <span className="text-text-muted text-sm font-mono">/</span>
            <span className="text-text text-sm font-medium">Admin &mdash; Users</span>
          </div>

          <Link
            href="/dashboard"
            className="text-[13px] text-text-muted hover:text-text font-medium"
          >
            &larr; Back to dashboard
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-[20px] font-semibold text-text tracking-tight">
              User Management
            </h1>
            <p className="text-xs text-text-muted mt-1">
              Search accounts, assign roles, and manage permissions. System currently has {total} registered users.
            </p>
          </div>

          <form onSubmit={handleSearchSubmit} className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Search by username or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="px-3 py-1.5 text-sm bg-surface border border-border rounded-[4px] text-text placeholder:text-text-muted focus:outline-none focus:border-accent w-64"
            />
            <button
              type="submit"
              disabled={loadingUsers}
              className="btn-secondary text-xs"
            >
              {loadingUsers ? "Searching..." : "Search"}
            </button>
            {search && (
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  fetchUsers("");
                }}
                className="text-xs text-text-muted hover:text-text px-2 py-1"
              >
                Clear
              </button>
            )}
          </form>
        </div>

        {error && (
          <div
            role="alert"
            className="p-3 bg-surface border border-danger/40 rounded-[6px] text-danger text-sm font-medium flex items-center justify-between"
          >
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-xs text-danger/70 hover:text-danger ml-4 font-mono"
            >
              Dismiss
            </button>
          </div>
        )}

        {success && (
          <div
            role="status"
            className="p-3 bg-surface border border-success/40 rounded-[6px] text-success text-sm font-medium flex items-center justify-between"
          >
            <span>{success}</span>
            <button
              onClick={() => setSuccess(null)}
              className="text-xs text-success/70 hover:text-success ml-4 font-mono"
            >
              Dismiss
            </button>
          </div>
        )}

        <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-bg/50">
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    User
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Display Name
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Email
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Role
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Last Sign-in
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Joined
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-text-muted text-sm">
                      {loadingUsers ? "Loading users..." : "No users found matching query."}
                    </td>
                  </tr>
                ) : (
                  users.map((u) => {
                    const currentSelectedRole = selectedRoles[u.id] || u.role;
                    const hasChanged = currentSelectedRole !== u.role;
                    const isSaving = savingUserId === u.id;
                    const lastLoginStr = u.last_login_at
                      ? new Date(u.last_login_at).toISOString().replace("T", " ").replace(/\..+/, " UTC")
                      : "—";
                    const createdStr = u.created_at
                      ? new Date(u.created_at).toISOString().split("T")[0]
                      : "—";

                    return (
                      <tr key={u.id} className="hover:bg-bg/40 transition-colors">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2.5">
                            {u.avatar_url ? (
                              <Image
                                src={u.avatar_url}
                                alt={u.username}
                                width={24}
                                height={24}
                                unoptimized
                                className="w-6 h-6 rounded-[3px] border border-border shrink-0 object-cover"
                              />
                            ) : (
                              <div className="w-6 h-6 rounded-[3px] bg-bg border border-border flex items-center justify-center text-[10px] font-mono text-text-muted">
                                {u.username.slice(0, 2).toUpperCase()}
                              </div>
                            )}
                            <a
                              href={`https://github.com/${u.username}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-mono text-[13px] text-accent hover:underline font-medium"
                            >
                              {u.username}
                            </a>
                            {u.id === currentUser.id && (
                              <span className="text-[10px] uppercase font-mono px-1 py-0.5 rounded-[3px] bg-accent/10 text-accent font-semibold">
                                You
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-text text-[13px]">
                          {u.display_name || "—"}
                        </td>
                        <td className="py-3 px-4 font-mono text-[12px] text-text-muted">
                          {u.email || "—"}
                        </td>
                        <td className="py-3 px-4">
                          <select
                            value={currentSelectedRole}
                            onChange={(e) =>
                              handleRoleChange(
                                u.id,
                                e.target.value as "student" | "faculty" | "admin"
                              )
                            }
                            disabled={isSaving}
                            className="text-xs bg-surface border border-border rounded-[4px] px-2 py-1 text-text capitalize focus:outline-none focus:border-accent"
                          >
                            <option value="student">Student</option>
                            <option value="faculty">Faculty</option>
                            <option value="admin">Admin</option>
                          </select>
                        </td>
                        <td className="py-3 px-4 font-mono text-[12px] text-text-muted">
                          {lastLoginStr}
                        </td>
                        <td className="py-3 px-4 font-mono text-[12px] text-text-muted">
                          {createdStr}
                        </td>
                        <td className="py-3 px-4 text-right">
                          {hasChanged ? (
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={() => handleSaveRole(u)}
                                disabled={isSaving}
                                className="px-2.5 py-1 text-xs font-medium rounded-[4px] bg-accent text-white hover:bg-accent-hover transition-colors disabled:opacity-50"
                              >
                                {isSaving ? "Saving..." : "Save"}
                              </button>
                              <button
                                onClick={() =>
                                  setSelectedRoles((prev) => ({
                                    ...prev,
                                    [u.id]: u.role,
                                  }))
                                }
                                disabled={isSaving}
                                className="px-2 py-1 text-xs text-text-muted hover:text-text"
                              >
                                Reset
                              </button>
                            </div>
                          ) : (
                            <span className="text-xs text-text-muted font-mono">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}
