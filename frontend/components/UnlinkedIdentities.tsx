"use client";

import React, { useState } from "react";
import { MemberDetail, UnlinkedAlias, assignAlias } from "@/lib/api";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface UnlinkedIdentitiesProps {
  projectId: string;
  unlinkedAliases: UnlinkedAlias[];
  members: MemberDetail[];
  onDataChanged?: () => void;
  readOnly?: boolean;
}

export default function UnlinkedIdentities({
  projectId,
  unlinkedAliases,
  members,
  onDataChanged,
  readOnly = false,
}: UnlinkedIdentitiesProps) {
  const [selectedMemberForAlias, setSelectedMemberForAlias] = useState<Record<string, string>>({});
  const [actionLoading, setActionLoading] = useState(false);

  const safeAliases = Array.isArray(unlinkedAliases) ? unlinkedAliases : [];
  const safeMembers = Array.isArray(members) ? members : [];

  if (safeAliases.length === 0) {
    return null;
  }

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

  return (
    <SectionErrorBoundary title="Unlinked Identities">
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
            Unlinked identities
          </h2>
          <span className="font-mono text-[12px] text-text-muted">
            {safeAliases.length} {safeAliases.length === 1 ? "identity" : "identities"}
          </span>
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
                      {a.commit_count === 1 ? "1 commit" : `${a.commit_count} commits`}
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
      </section>
    </SectionErrorBoundary>
  );
}

