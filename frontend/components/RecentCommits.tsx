"use client";

import React from "react";
import { CommitItem } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface RecentCommitsProps {
  commits: CommitItem[];
}

export default function RecentCommits({ commits }: RecentCommitsProps) {
  const safeCommits = Array.isArray(commits) ? commits : [];

  return (
    <SectionErrorBoundary title="Recent Commits">
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
            Recent commits
          </h2>
          <span className="font-mono text-[12px] text-text-muted">
            {safeCommits.length === 1 ? "1 commit" : `${safeCommits.length} commits`}
          </span>
        </div>
        <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-bg/50">
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    SHA
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Author
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Date (UTC)
                  </th>
                  <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                    Subject
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-[13px]">
                {safeCommits.map((c) => {
                  const dateStr = formatDateTime(c.authored_at);
                  const shaShort =
                    typeof c.sha === "string" && c.sha.length >= 7
                      ? c.sha.slice(0, 7)
                      : c.sha || "—";

                  return (
                    <tr key={c.id} className="hover:bg-bg/40 transition-colors duration-120">
                      <td className="py-2 px-4 font-mono font-medium text-accent">
                        {shaShort}
                      </td>
                      <td className="py-2 px-4 text-text">{c.author_name || "Unknown"}</td>
                      <td className="py-2 px-4 font-mono text-text-muted tabular-nums">
                        {dateStr}
                      </td>
                      <td className="py-2 px-4 text-text truncate max-w-[400px]">
                        {c.subject || "No commit message"}
                      </td>
                    </tr>
                  );
                })}
                {safeCommits.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-4 px-4 text-center text-text-muted font-sans text-sm">
                      No commits recorded.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </SectionErrorBoundary>
  );
}

