"use client";

import React, { useState } from "react";
import Image from "next/image";
import { ProjectFacultyItem, ProjectReviewerItem, inviteProjectReviewer, removeProjectReviewer } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/date";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface ReviewersPanelProps {
  projectId: string;
  reviewers: Array<ProjectReviewerItem | ProjectFacultyItem>;
  isOwnerOrAdmin: boolean;
  onReviewersUpdated: () => void;
  hideHeader?: boolean;
}

export default function ReviewersPanel({
  projectId,
  reviewers,
  isOwnerOrAdmin,
  onReviewersUpdated,
  hideHeader = false,
}: ReviewersPanelProps) {
  const [inputVal, setInputVal] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const safeReviewers = Array.isArray(reviewers) ? reviewers : [];

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputVal.trim()) return;
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await inviteProjectReviewer(projectId, inputVal.trim());
      if (res.ok) {
        setSuccess(`Reviewer "${inputVal.trim()}" invited successfully.`);
        setInputVal("");
        onReviewersUpdated();
      } else {
        setError(res.error || "Failed to invite reviewer.");
      }
    } catch {
      setError("Network error while inviting reviewer.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemove = async (reviewerId: string) => {
    if (!confirm("Are you sure you want to remove this reviewer?")) return;
    try {
      const res = await removeProjectReviewer(projectId, reviewerId);
      if (res.ok) {
        onReviewersUpdated();
      } else {
        alert(res.error || "Failed to remove reviewer.");
      }
    } catch {
      alert("Network error while removing reviewer.");
    }
  };

  return (
    <SectionErrorBoundary title="Project Reviewers">
      <section className="space-y-3">
        {!hideHeader && (
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
                Project Reviewers
              </h2>
              <p className="text-xs text-text-muted mt-0.5">
                Invited reviewers with review and dispute oversight access.
              </p>
            </div>
          </div>
        )}

        {success && (
          <div className="p-2.5 bg-success/10 border border-success/30 rounded-[4px] text-xs text-success flex items-center justify-between">
            <span>{success}</span>
            <button onClick={() => setSuccess(null)} className="text-xs text-success/70 hover:text-success">
              Dismiss
            </button>
          </div>
        )}

        {error && (
          <div className="p-2.5 bg-danger/10 border border-danger/30 rounded-[4px] text-xs text-danger flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-xs text-danger/70 hover:text-danger">
              Dismiss
            </button>
          </div>
        )}

        <div className={hideHeader ? "space-y-4" : "bg-surface border border-border rounded-[6px] p-4 space-y-4"}>
          {isOwnerOrAdmin && (
            <form onSubmit={handleAdd} className="flex items-center gap-2">
              <input
                type="text"
                placeholder="GitHub username to invite..."
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                disabled={submitting}
                className="text-[13px] h-[32px] px-3 bg-surface border border-border rounded-[4px] text-text flex-1 max-w-[300px] focus:outline-none focus:border-accent"
              />
              <button
                type="submit"
                disabled={submitting || !inputVal.trim()}
                className="btn-secondary h-[32px] px-3 text-[13px]"
              >
                {submitting ? "Inviting..." : "Invite reviewer"}
              </button>
            </form>
          )}

          {safeReviewers.length === 0 ? (
            <p className="text-xs text-text-muted">No reviewers currently invited to this project.</p>
          ) : (
            <div className={`divide-y divide-border ${isOwnerOrAdmin ? "border-t border-border pt-2" : ""}`}>
              {safeReviewers.map((f) => {
                const username =
                  ("invitee_username" in f && f.invitee_username) ||
                  ("username" in f && f.username) ||
                  "unknown";
                const initial =
                  typeof username === "string" && username.length > 0
                    ? username.slice(0, 2).toUpperCase()
                    : "??";
                const reviewerUserId =
                  f.id ||
                  ("user_id" in f && f.user_id) ||
                  ("faculty_user_id" in f && f.faculty_user_id) ||
                  "";
                const avatar = "avatar_url" in f ? f.avatar_url : undefined;
                const displayName = "display_name" in f ? f.display_name : undefined;

                return (
                  <div key={f.id} className="py-2.5 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-2.5">
                      {avatar ? (
                        <Image
                          src={avatar}
                          alt={username}
                          width={24}
                          height={24}
                          unoptimized
                          className="w-6 h-6 rounded-[3px] border border-border object-cover"
                        />
                      ) : (
                        <div className="w-6 h-6 rounded-[3px] bg-bg border border-border flex items-center justify-center text-[10px] font-mono text-text-muted">
                          {initial}
                        </div>
                      )}
                      <div>
                        <span className="font-mono text-[13px] font-medium text-text">{username}</span>
                        {displayName && (
                          <span className="ml-2 text-xs text-text-muted">({displayName})</span>
                        )}
                        {f.status && (
                          <span className="ml-2 font-mono text-[10px] uppercase px-1.5 py-0.2 rounded border border-border text-text-muted">
                            {f.status}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[11px] text-text-muted">
                        {f.created_at ? `Invited ${formatDate(f.created_at)}` : "—"}
                        {f.responded_at ? ` · Responded ${formatDateTime(f.responded_at)}` : ""}
                      </span>
                      {isOwnerOrAdmin && (
                        <button
                          type="button"
                          onClick={() => handleRemove(reviewerUserId)}
                          className="text-xs text-danger/80 hover:text-danger font-medium"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </SectionErrorBoundary>
  );
}
