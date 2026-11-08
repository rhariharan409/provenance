"use client";

import { useState } from "react";
import Link from "next/link";
import { UserPassportItem, revokePassport } from "@/lib/api";

interface MyPassportsTableProps {
  initialPassports: UserPassportItem[];
}

export default function MyPassportsTable({ initialPassports }: MyPassportsTableProps) {
  const [passports, setPassports] = useState<UserPassportItem[]>(initialPassports);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [revokingCode, setRevokingCode] = useState<string | null>(null);
  const [confirmRevokeCode, setConfirmRevokeCode] = useState<string | null>(null);

  if (!passports || passports.length === 0) {
    return null;
  }

  const handleCopy = (code: string) => {
    const url = `${window.location.origin}/p/${code}`;
    navigator.clipboard.writeText(url);
    setCopiedCode(code);
    setTimeout(() => {
      setCopiedCode((prev) => (prev === code ? null : prev));
    }, 2000);
  };

  const handleRevoke = async (code: string) => {
    setRevokingCode(code);
    try {
      const ok = await revokePassport(code);
      if (ok) {
        setPassports((prev) =>
          prev.map((p) => (p.code === code ? { ...p, status: "revoked" } : p))
        );
      }
    } finally {
      setRevokingCode(null);
      setConfirmRevokeCode(null);
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[16px] font-semibold text-text tracking-tight">
          My passports
        </h2>
      </div>

      <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-border bg-bg/50">
                <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                  Code
                </th>
                <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                  Project
                </th>
                <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                  Share
                </th>
                <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                  Created (UTC)
                </th>
                <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                  Views
                </th>
                <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                  Disputes
                </th>
                <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {passports.map((p) => {
                const createdStr = p.created_at
                  ? new Date(p.created_at)
                      .toISOString()
                      .replace("T", " ")
                      .replace(/\..+/, "")
                  : "—";

                let disputeStatusStr = "No disputes";
                if (p.dispute_summary.open > 0) {
                  disputeStatusStr = `${p.dispute_summary.open} open`;
                } else if (p.dispute_summary.resolved > 0) {
                  disputeStatusStr = `${p.dispute_summary.resolved} resolved`;
                } else if (p.dispute_summary.rejected > 0) {
                  disputeStatusStr = `${p.dispute_summary.rejected} reviewed`;
                }

                const isRevoked = p.status === "revoked";

                return (
                  <tr key={p.id} className="hover:bg-bg/40 transition-colors duration-120">
                    <td className="py-3 px-4 font-mono text-[13px] text-text font-medium">
                      {p.code.slice(0, 10)}...
                      {isRevoked && (
                        <span className="ml-2 text-[11px] font-sans border border-border px-1.5 py-0.2 rounded-[3px] text-text-muted">
                          revoked
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-medium text-text">
                      <Link
                        href={`/projects/${p.project_id}`}
                        className="hover:underline text-accent"
                      >
                        {p.project_name}
                      </Link>
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-[13px] tabular-nums text-text">
                      {p.share_percent.toFixed(2)}%
                    </td>
                    <td className="py-3 px-4 font-mono text-[13px] tabular-nums text-text-muted">
                      {createdStr}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-[13px] tabular-nums text-text">
                      {p.view_count.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-[13px] text-text-muted">
                      <span
                        className={
                          p.dispute_summary.open > 0
                            ? "text-warning font-medium"
                            : ""
                        }
                      >
                        {disputeStatusStr}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2 text-[13px]">
                        {!isRevoked ? (
                          <>
                            <a
                              href={`/p/${p.code}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-accent hover:underline font-medium"
                            >
                              Open
                            </a>
                            <span className="text-border">|</span>
                            <button
                              onClick={() => handleCopy(p.code)}
                              className="text-text hover:text-accent transition-colors"
                            >
                              {copiedCode === p.code ? "Copied!" : "Copy link"}
                            </button>
                            <span className="text-border">|</span>
                            {confirmRevokeCode === p.code ? (
                              <div className="inline-flex items-center gap-1.5">
                                <button
                                  onClick={() => handleRevoke(p.code)}
                                  disabled={revokingCode === p.code}
                                  className="text-danger hover:underline font-medium"
                                >
                                  {revokingCode === p.code ? "Revoking..." : "Confirm"}
                                </button>
                                <button
                                  onClick={() => setConfirmRevokeCode(null)}
                                  className="text-text-muted hover:underline"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setConfirmRevokeCode(p.code)}
                                className="text-danger hover:underline"
                              >
                                Revoke
                              </button>
                            )}
                          </>
                        ) : (
                          <span className="text-text-muted">Revoked</span>
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
    </section>
  );
}
