"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  ReviewInvitationItem,
  ReviewedProjectItem,
  acceptReviewInvitation,
  declineReviewInvitation,
  leaveReviewedProject,
  getReviewedProjects,
} from "@/lib/api";
import { formatDate } from "@/lib/date";

interface ReviewClientPageProps {
  initialInvitations: ReviewInvitationItem[];
  initialProjects: ReviewedProjectItem[];
}

export default function ReviewClientPage({
  initialInvitations,
  initialProjects,
}: ReviewClientPageProps) {
  const [invitations, setInvitations] = useState<ReviewInvitationItem[]>(initialInvitations);
  const [projects, setProjects] = useState<ReviewedProjectItem[]>(initialProjects);
  const [processingInvId, setProcessingInvId] = useState<string | null>(null);
  const [invError, setInvError] = useState<string | null>(null);

  const [confirmLeaveId, setConfirmLeaveId] = useState<string | null>(null);
  const [leavingId, setLeavingId] = useState<string | null>(null);
  const [leaveError, setLeaveError] = useState<string | null>(null);

  const handleAccept = async (inv: ReviewInvitationItem) => {
    setProcessingInvId(inv.id);
    setInvError(null);
    try {
      const res = await acceptReviewInvitation(inv.id);
      if (res.ok) {
        setInvitations((prev) => prev.filter((item) => item.id !== inv.id));
        // Refresh reviewed projects
        const updatedProjects = await getReviewedProjects();
        if (updatedProjects && updatedProjects.length > 0) {
          setProjects(updatedProjects);
        } else {
          // Fallback optimistic add if projects endpoint has momentary lag
          setProjects((prev) => [
            {
              id: inv.project_id,
              name: inv.project_name,
              repo_name: inv.repo_name || inv.repo_full_name,
              repo_full_name: inv.repo_full_name || inv.repo_name,
              status: "ready",
              member_count: 0,
              open_disputes_count: 0,
              flags_count: 0,
              accepted_at: new Date().toISOString(),
              created_at: new Date().toISOString(),
            },
            ...prev,
          ]);
        }
      } else {
        setInvError(res.error || "Failed to accept invitation.");
      }
    } catch {
      setInvError("Network error accepting invitation.");
    } finally {
      setProcessingInvId(null);
    }
  };

  const handleDecline = async (invId: string) => {
    setProcessingInvId(invId);
    setInvError(null);
    try {
      const res = await declineReviewInvitation(invId);
      if (res.ok) {
        setInvitations((prev) => prev.filter((item) => item.id !== invId));
      } else {
        setInvError(res.error || "Failed to decline invitation.");
      }
    } catch {
      setInvError("Network error declining invitation.");
    } finally {
      setProcessingInvId(null);
    }
  };

  const handleLeave = async (projectId: string) => {
    setLeavingId(projectId);
    setLeaveError(null);
    try {
      const res = await leaveReviewedProject(projectId);
      if (res.ok) {
        setProjects((prev) => prev.filter((item) => item.id !== projectId));
        setConfirmLeaveId(null);
      } else {
        setLeaveError(res.error || "Failed to leave review.");
      }
    } catch {
      setLeaveError("Network error leaving review.");
    } finally {
      setLeavingId(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* Invitations Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[18px] font-semibold text-text tracking-tight">
              Invitations
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              Review requests from project owners.
            </p>
          </div>
          {invitations.length > 0 && (
            <span className="text-xs font-mono text-text-muted">
              {invitations.length} pending
            </span>
          )}
        </div>

        {invError && (
          <div className="p-3 bg-danger/10 border border-danger/30 rounded-[4px] text-xs text-danger">
            {invError}
          </div>
        )}

        {invitations.length === 0 ? (
          <div className="bg-surface border border-border rounded-[6px] p-6 text-center text-sm text-text-muted">
            No review invitations. When someone invites you to review a project, it will appear here.
          </div>
        ) : (
          <div className="space-y-3">
            {invitations.map((inv) => {
              const isBusy = processingInvId === inv.id;
              const dateStr = formatDate(inv.created_at);

              return (
                <div
                  key={inv.id}
                  className="bg-surface border border-border rounded-[6px] p-5 space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
                    <div className="space-y-1">
                      <span className="font-mono text-[14px] font-semibold text-text">
                        {inv.repo_name || inv.repo_full_name || inv.project_name}
                      </span>
                      <div className="flex items-center gap-3 text-xs text-text-muted">
                        <span>
                          Invited by:{" "}
                          <strong className="text-text font-normal">
                            {inv.invited_by}
                          </strong>
                        </span>
                        <span aria-hidden="true">&bull;</span>
                        <span>{dateStr}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-start sm:self-auto">
                      <button
                        type="button"
                        onClick={() => handleAccept(inv)}
                        disabled={isBusy}
                        className="btn-primary text-xs h-[30px] px-3 font-medium"
                      >
                        {isBusy ? "Processing..." : "Accept"}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDecline(inv.id)}
                        disabled={isBusy}
                        className="btn-secondary text-xs h-[30px] px-3"
                      >
                        Decline
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="space-y-1">
                      <span className="font-semibold text-text text-[11px] uppercase tracking-wider text-text-muted">
                        You will be able to see:
                      </span>
                      <p className="text-text-muted">
                        scores, flags and evidence, summaries, originality results, disputes.
                      </p>
                    </div>
                    <div className="space-y-1">
                      <span className="font-semibold text-text text-[11px] uppercase tracking-wider text-text-muted">
                        You will not see:
                      </span>
                      <p className="text-text-muted">
                        the owner&apos;s private credentials or settings.
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Projects I review Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[18px] font-semibold text-text tracking-tight">
              Projects I review
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              Repositories you have accepted to evaluate and provide feedback on.
            </p>
          </div>
          <span className="text-xs font-mono text-text-muted">
            {projects.length} {projects.length === 1 ? "project" : "projects"}
          </span>
        </div>

        {leaveError && (
          <div className="p-3 bg-danger/10 border border-danger/30 rounded-[4px] text-xs text-danger">
            {leaveError}
          </div>
        )}

        {projects.length === 0 ? (
          <div className="bg-surface border border-border rounded-[6px] p-6 text-center text-sm text-text-muted">
            You are not currently reviewing any projects.
          </div>
        ) : (
          <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border bg-bg/50">
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                      Repo Name
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Members
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Open Disputes
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Flags
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                      Accepted Date
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {projects.map((p) => {
                    const acceptedStr = formatDate(p.accepted_at || p.created_at);
                    const isConfirming = confirmLeaveId === p.id;
                    const isLeaving = leavingId === p.id;

                    return (
                      <tr
                        key={p.id}
                        className="hover:bg-bg/40 transition-colors duration-120"
                      >
                        <td className="py-3 px-4">
                          <Link
                            href={`/review/${p.id}`}
                            className="font-mono text-[13px] text-accent hover:underline font-medium"
                          >
                            {p.repo_name || p.repo_full_name || p.name}
                          </Link>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-[13px] tabular-nums text-text">
                          {p.member_count ?? 0}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-[13px] tabular-nums">
                          {p.open_disputes_count > 0 ? (
                            <span className="inline-block px-2 py-0.5 rounded-[4px] bg-danger/10 text-danger font-medium border border-danger/20">
                              {p.open_disputes_count} open
                            </span>
                          ) : (
                            <span className="text-text-muted">0</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-[13px] tabular-nums">
                          {p.flags_count > 0 ? (
                            <span className="inline-block px-2 py-0.5 rounded-[4px] bg-warning/10 text-warning font-medium border border-warning/20">
                              {p.flags_count} flagged
                            </span>
                          ) : (
                            <span className="text-text-muted">0</span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono text-[12px] text-text-muted">
                          {acceptedStr}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Link
                              href={`/review/${p.id}`}
                              className="btn-primary text-xs h-[28px] px-2.5 font-medium"
                            >
                              Open review
                            </Link>

                            {isConfirming ? (
                              <div className="inline-flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => handleLeave(p.id)}
                                  disabled={isLeaving}
                                  className="btn-secondary text-xs h-[28px] px-2.5 border-danger text-danger hover:bg-danger/5"
                                >
                                  {isLeaving ? "Leaving..." : "Confirm leave"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setConfirmLeaveId(null)}
                                  className="btn-secondary text-xs h-[28px] px-2"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                onClick={() => setConfirmLeaveId(p.id)}
                                className="btn-secondary text-xs h-[28px] px-2.5 text-text-muted hover:text-danger"
                              >
                                Leave review
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

