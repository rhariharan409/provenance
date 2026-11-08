"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCurrentUser, deleteMyAccount, exportMyData, UserProfile } from "@/lib/api";

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    async function loadUser() {
      try {
        const u = await getCurrentUser();
        if (!u) {
          router.replace("/");
          return;
        }
        setUser(u);
      } catch {
        router.replace("/");
      } finally {
        setLoading(false);
      }
    }
    loadUser();
  }, [router]);

  const handleExportData = async () => {
    if (!user) return;
    setExporting(true);
    setError(null);
    try {
      const data = await exportMyData();
      if (!data) {
        setError("Failed to export data.");
        return;
      }
      const jsonStr = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonStr], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `provenance-data-${user.username}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setSuccess("Account data snapshot downloaded successfully.");
    } catch {
      setError("An error occurred while exporting your data.");
    } finally {
      setExporting(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!user || deleteConfirmText !== "DELETE") return;

    if (
      !confirm(
        "Are you absolutely certain you want to permanently delete your account and all associated projects and passports? This action cannot be undone."
      )
    ) {
      return;
    }

    setDeleting(true);
    setError(null);
    try {
      const res = await deleteMyAccount("DELETE");
      if (res.ok) {
        // Redirect to landing page with message
        router.push("/?message=account_deleted");
      } else {
        setError(res.error || "Failed to delete account.");
        setDeleting(false);
      }
    } catch {
      setError("An unexpected error occurred while deleting your account.");
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center text-text-muted text-sm">
        Loading account details...
      </div>
    );
  }

  if (!user) return null;

  const formattedCreated = user.created_at
    ? new Date(user.created_at).toISOString().replace("T", " ").replace(/\..+/, " UTC")
    : "—";
  const formattedLastLogin = user.last_login_at
    ? new Date(user.last_login_at).toISOString().replace("T", " ").replace(/\..+/, " UTC")
    : "—";

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
            <span className="text-text text-sm font-medium">Account Settings</span>
          </div>

          <Link
            href="/dashboard"
            className="text-[13px] text-text-muted hover:text-text font-medium"
          >
            &larr; Back to dashboard
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-[760px] w-full mx-auto px-4 py-8 space-y-8">
        <div>
          <h1 className="text-[22px] font-semibold text-text tracking-tight">
            Account Settings
          </h1>
          <p className="text-xs text-text-muted mt-1">
            Manage your personal profile, exported records, and data retention settings.
          </p>
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

        {/* Profile Card */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-6">
          <div className="flex items-center gap-4">
            {user.avatar_url ? (
              <Image
                src={user.avatar_url}
                alt={user.username}
                width={56}
                height={56}
                unoptimized
                className="w-14 h-14 rounded-[6px] border border-border shrink-0 object-cover"
              />
            ) : (
              <div className="w-14 h-14 rounded-[6px] bg-bg border border-border flex items-center justify-center text-base font-mono font-medium text-text-muted">
                {user.username.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div>
              <h2 className="text-base font-semibold text-text">
                {user.display_name || user.username}
              </h2>
              <p className="text-xs font-mono text-text-muted">@{user.username}</p>
              <div className="mt-1">
                <span className="text-[11px] font-medium uppercase font-mono px-2 py-0.5 rounded-[3px] bg-bg border border-border text-text">
                  Role: {user.role}
                </span>
              </div>
            </div>
          </div>

          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm border-t border-border pt-4">
            <div>
              <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                Email
              </dt>
              <dd className="font-mono text-[13px] text-text">
                {user.email || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                GitHub ID
              </dt>
              <dd className="font-mono text-[13px] text-text">
                {user.github_id}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                Account Created
              </dt>
              <dd className="font-mono text-[12px] text-text-muted">
                {formattedCreated}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                Last Sign-in
              </dt>
              <dd className="font-mono text-[12px] text-text-muted">
                {formattedLastLogin}
              </dd>
            </div>
          </dl>
        </section>

        {/* Data Export Section */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Export Personal Data
            </h2>
            <p className="text-xs text-text-muted mt-1 leading-relaxed">
              Download a machine-readable JSON snapshot containing your profile metadata, owned projects,
              published passports, and raised dispute history.
            </p>
          </div>

          <button
            onClick={handleExportData}
            disabled={exporting}
            className="btn-secondary text-xs"
          >
            {exporting ? "Generating snapshot..." : "Download my data (JSON)"}
          </button>
        </section>

        {/* Delete Account Section */}
        <section className="bg-surface border border-danger/40 rounded-[6px] p-6 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-danger">
              Danger Zone &mdash; Delete Account
            </h2>
            <p className="text-xs text-text-muted mt-1 leading-relaxed">
              Deleting your account will permanently remove all your projects, passports, and analysis history.
              Repositories on GitHub are not affected. This action is irreversible.
            </p>
          </div>

          <div className="space-y-3 pt-2 border-t border-border">
            <label className="block text-xs font-medium text-text">
              To confirm, type <span className="font-mono font-bold text-danger">DELETE</span> below:
            </label>
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <input
                type="text"
                placeholder="Type DELETE"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                disabled={deleting}
                className="px-3 py-1.5 text-sm bg-surface border border-border rounded-[4px] text-text placeholder:text-text-muted font-mono w-full sm:w-48 focus:outline-none focus:border-danger"
              />
              <button
                onClick={handleDeleteAccount}
                disabled={deleteConfirmText !== "DELETE" || deleting}
                className="px-4 py-2 text-xs font-semibold rounded-[4px] bg-danger text-white hover:bg-danger/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
              >
                {deleting ? "Deleting account..." : "Permanently delete account"}
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
