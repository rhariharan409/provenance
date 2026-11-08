"use client";

import React, { useState } from "react";
import { MemberDetail, UnlinkedAlias, assignAlias, mergeMembers } from "@/lib/api";
import { formatDate } from "@/lib/date";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface MembersPanelProps {
  projectId: string;
  members: MemberDetail[];
  unlinkedAliases: UnlinkedAlias[];
  onDataChanged?: () => void;
  readOnly?: boolean;
}

export default function MembersPanel({
  projectId,
  members,
  unlinkedAliases,
  onDataChanged,
  readOnly = false,
}: MembersPanelProps) {
  const [selectedMemberForAlias, setSelectedMemberForAlias] = useState<Record<string, string>>({});
  const [mergeSource, setMergeSource] = useState<string>("");
  const [mergeTarget, setMergeTarget] = useState<string>("");
  const [confirmMerge, setConfirmMerge] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const safeMembers = Array.isArray(members) ? members : [];
  const safeAliases = Array.isArray(unlinkedAliases) ? unlinkedAliases : [];

  const handleAssign = async (aliasId: string) => {
    const memberId = selectedMemberForAlias[aliasId];
    if (!memberId) return;

    setActionLoading(true);
    const ok = await assignAlias(projectId, aliasId, memberId);
    setActionLoading(false);

    if (ok) {
      onDataChanged?.();
    } else {
      alert("Failed to assign alias to member.");
    }
  };

  const handleMerge = async () => {
    if (!mergeSource || !mergeTarget || mergeSource === mergeTarget) return;

    if (!confirmMerge) {
      setConfirmMerge(true);
      return;
    }

    setActionLoading(true);
    const ok = await mergeMembers(projectId, mergeSource, mergeTarget);
    setActionLoading(false);
    setConfirmMerge(false);

    if (ok) {
      setMergeSource("");
      setMergeTarget("");
      onDataChanged?.();
    } else {
      alert("Failed to merge members.");
    }
  };

  return (
    <SectionErrorBoundary title="Team Members">
      <div className="space-y-6">
        {/* Members Table */}
        <section className="space-y-3">
          <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
            Members
          </h2>
          <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border bg-bg/50">
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                      Login
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Commits
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Additions (+)
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Deletions (-)
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      PRs
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                      Reviews
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                      First Commit (UTC)
                    </th>
                    <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                      Last Commit (UTC)
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border font-mono text-[13px]">
                  {safeMembers.map((m) => {
                    const firstStr = formatDate(m.first_commit_at);
                    const lastStr = formatDate(m.last_commit_at);

                    return (
                      <tr key={m.id} className="hover:bg-bg/40 transition-colors duration-120">
                        <td className="py-2.5 px-4 font-medium text-text">
                          {m.login || "unknown"}
                          {m.display_name && (
                            <span className="font-sans text-text-muted text-[12px] ml-2">
                              ({m.display_name})
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums text-text">
                          {(m.commit_count || 0).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums text-success">
                          +{(m.additions || 0).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums text-danger">
                          -{(m.deletions || 0).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums text-text">
                          {m.pull_requests_opened ?? 0}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums text-text">
                          {m.reviews_given ?? 0}
                        </td>
                        <td className="py-2.5 px-4 tabular-nums text-text-muted">
                          {firstStr}
                        </td>
                        <td className="py-2.5 px-4 tabular-nums text-text-muted">
                          {lastStr}
                        </td>
                      </tr>
                    );
                  })}
                  {safeMembers.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-4 px-4 text-center text-text-muted font-sans text-sm">
                        No members resolved yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Unlinked Identities & Merge Controls */}
        {safeAliases.length > 0 && (
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
                Unlinked identities
              </h2>
            </div>

            <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border bg-bg/50">
                      <th className="py-2 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Author name
                      </th>
                      <th className="py-2 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Email
                      </th>
                      <th className="py-2 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                        Commits
                      </th>
                      {!readOnly && (
                        <th className="py-2 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                          Assign to member
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border font-mono text-[13px]">
                    {safeAliases.map((a) => (
                      <tr key={a.id} className="hover:bg-bg/40 transition-colors duration-120">
                        <td className="py-2 px-4 text-text">{a.name}</td>
                        <td className="py-2 px-4 text-text-muted">{a.email}</td>
                        <td className="py-2 px-4 text-right tabular-nums text-text">
                          {a.commit_count}
                        </td>
                        {!readOnly && (
                          <td className="py-2 px-4 font-sans">
                            <div className="flex items-center gap-2">
                              <select
                                aria-label={`Assign member for ${a.name}`}
                                value={selectedMemberForAlias[a.id] || ""}
                                onChange={(e) =>
                                  setSelectedMemberForAlias({
                                    ...selectedMemberForAlias,
                                    [a.id]: e.target.value,
                                  })
                                }
                                className="h-[30px] px-2 text-[12px] bg-surface border border-border rounded-[4px] text-text focus:outline-none"
                              >
                                <option value="">Select member...</option>
                                {safeMembers.map((m) => (
                                  <option key={m.id} value={m.id}>
                                    {m.login}
                                  </option>
                                ))}
                              </select>
                              <button
                                type="button"
                                onClick={() => handleAssign(a.id)}
                                disabled={actionLoading || !selectedMemberForAlias[a.id]}
                                className="btn-secondary h-[30px] px-2.5 text-[12px]"
                              >
                                Assign
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Merge Members Control for Owners */}
            {safeMembers.length > 1 && !readOnly && (
              <div className="bg-surface border border-border rounded-[6px] p-4 space-y-3">
                <h3 className="text-[13px] font-semibold text-text uppercase tracking-wider text-text-muted">
                  Merge members
                </h3>
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-text-muted text-[13px]">Move from:</span>
                    <select
                      aria-label="Source member to merge from"
                      value={mergeSource}
                      onChange={(e) => setMergeSource(e.target.value)}
                      className="h-[32px] px-2 font-mono text-[13px] bg-surface border border-border rounded-[4px] text-text focus:outline-none"
                    >
                      <option value="">Select source member...</option>
                      {safeMembers.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.login}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-text-muted text-[13px]">into:</span>
                    <select
                      aria-label="Target member to merge into"
                      value={mergeTarget}
                      onChange={(e) => setMergeTarget(e.target.value)}
                      className="h-[32px] px-2 font-mono text-[13px] bg-surface border border-border rounded-[4px] text-text focus:outline-none"
                    >
                      <option value="">Select target member...</option>
                      {safeMembers.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.login}
                        </option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="button"
                    onClick={handleMerge}
                    disabled={
                      actionLoading ||
                      !mergeSource ||
                      !mergeTarget ||
                      mergeSource === mergeTarget
                    }
                    className={`btn-secondary h-[32px] px-3 text-[13px] ${
                      confirmMerge ? "border-danger text-danger" : ""
                    }`}
                  >
                    {confirmMerge ? "Confirm merge" : "Merge members"}
                  </button>
                </div>
              </div>
            )}
          </section>
        )}
      </div>
    </SectionErrorBoundary>
  );
}

