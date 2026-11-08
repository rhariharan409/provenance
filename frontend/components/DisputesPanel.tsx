"use client";

import React, { useState } from "react";
import { DisputeItem, MemberDetail, UserProfile, resolveDispute } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface DisputesPanelProps {
  projectId: string;
  disputes: DisputeItem[];
  members: MemberDetail[];
  currentUser: UserProfile | null;
  isOwnerOrAdmin: boolean;
  isAssignedFaculty: boolean;
  onDisputesChanged: () => void;
}

export default function DisputesPanel({
  projectId,
  disputes,
  members,
  currentUser,
  isOwnerOrAdmin,
  isAssignedFaculty,
  onDisputesChanged,
}: DisputesPanelProps) {
  const [resolutionNotes, setResolutionNotes] = useState<Record<string, string>>({});
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const safeDisputes = Array.isArray(disputes) ? disputes : [];
  const safeMembers = Array.isArray(members) ? members : [];

  if (!isOwnerOrAdmin && !isAssignedFaculty && safeDisputes.length === 0) {
    return null;
  }

  const handleResolve = async (disputeId: string, statusVal: "resolved" | "rejected") => {
    setResolvingId(disputeId);
    setNotice(null);
    try {
      const note = resolutionNotes[disputeId] || "";
      const res = await resolveDispute(projectId, disputeId, statusVal, note);
      if (res.ok) {
        setNotice(res.message || "Dispute updated.");
        onDisputesChanged();
      } else {
        setNotice(res.error || "Failed to update dispute.");
      }
    } catch {
      setNotice("Failed to update dispute.");
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <SectionErrorBoundary title="Disputes">
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
            Disputes
          </h2>
          <span className="font-mono text-[12px] text-text-muted">
            {safeDisputes.length} {safeDisputes.length === 1 ? "dispute" : "disputes"}
          </span>
        </div>

        {notice && (
          <div className="p-3 bg-surface border border-border rounded-[4px] text-[13px] text-text flex items-center justify-between">
            <span>{notice}</span>
            <button onClick={() => setNotice(null)} className="text-xs text-text-muted hover:text-text">
              Dismiss
            </button>
          </div>
        )}

        <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
          {safeDisputes.length === 0 ? (
            <div className="p-4 text-center text-text-muted text-[13px]">
              No disputes recorded for this project.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {safeDisputes.map((d) => {
                const dateStr = formatDateTime(d.created_at);
                const mem = safeMembers.find((x) => x.id === d.member_id);
                const memberLabel = mem ? (mem.display_name || mem.login || d.member_id) : (d.member_name || d.member_id);
                const isOpen = d.status === "open";
                const canResolve = (isOwnerOrAdmin || isAssignedFaculty) && isOpen && (currentUser?.role === "admin" || isAssignedFaculty || d.raised_by !== currentUser?.id);

                return (
                  <div key={d.id} className="p-4 space-y-3 text-[13px]">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-text">{memberLabel}</span>
                        <span className="font-mono text-[12px] text-text-muted">{dateStr}</span>
                      </div>
                      <span
                        className={`font-mono text-[11px] px-2 py-0.5 rounded-[3px] border uppercase ${
                          d.status === "open"
                            ? "border-warning text-warning bg-warning/5"
                            : d.status === "resolved"
                            ? "border-success text-success bg-success/5"
                            : "border-border text-text-muted bg-bg"
                        }`}
                      >
                        {d.status}
                      </span>
                    </div>

                    <p className="text-text font-sans whitespace-pre-wrap">{d.text}</p>

                    {d.resolution_note && (
                      <div className="p-2.5 bg-bg/50 border border-border rounded-[4px] text-[12px] text-text-muted">
                        <span className="font-medium text-text">Resolution note: </span>
                        {d.resolution_note}
                      </div>
                    )}

                    {isOpen && canResolve && (
                      <div className="pt-2 border-t border-border flex flex-col sm:flex-row gap-2 items-start sm:items-center">
                        <input
                          type="text"
                          placeholder="Resolution note (optional)..."
                          value={resolutionNotes[d.id] || ""}
                          onChange={(e) =>
                            setResolutionNotes({ ...resolutionNotes, [d.id]: e.target.value })
                          }
                          className="text-[12px] h-[30px] px-2.5 bg-surface border border-border rounded-[4px] text-text flex-1 min-w-[200px] focus:outline-none focus:ring-1 focus:ring-accent"
                        />
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => handleResolve(d.id, "resolved")}
                            disabled={resolvingId === d.id}
                            className="btn-primary text-[12px] h-[30px] px-3"
                          >
                            {resolvingId === d.id ? "Saving..." : "Resolve"}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleResolve(d.id, "rejected")}
                            disabled={resolvingId === d.id}
                            className="btn-secondary text-[12px] h-[30px] px-3"
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    )}
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

