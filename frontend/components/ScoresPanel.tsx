"use client";

import React, { useState } from "react";
import {
  ProjectScoresResponse,
  MemberEvidenceResponse,
  MemberDetail,
  UserProfile,
  publishPassport,
  createDispute,
  getMemberEvidence,
  triggerAnalysis,
  formatDate,
} from "@/lib/api";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface ScoresPanelProps {
  projectId: string;
  scores: ProjectScoresResponse | null;
  analysisStatus: string;
  analysisError: string | null;
  progressStep?: string | null;
  progressPercent?: number | null;
  members: MemberDetail[];
  currentUser: UserProfile | null;
  isOwnerOrAdmin: boolean;
  passportData: Record<string, { code: string; url: string }>;
  onAnalysisTriggered?: () => void;
  onPassportPublished?: (memberId: string, code: string, url: string) => void;
  onDisputeSubmitted?: () => void;
  readOnly?: boolean;
}

export default function ScoresPanel({
  projectId,
  scores,
  analysisStatus,
  analysisError,
  progressStep,
  progressPercent,
  members,
  currentUser,
  isOwnerOrAdmin,
  passportData,
  onAnalysisTriggered,
  onPassportPublished,
  onDisputeSubmitted,
  readOnly = false,
}: ScoresPanelProps) {
  const [expandedMember, setExpandedMember] = useState<string | null>(null);
  const [memberEvidences, setMemberEvidences] = useState<Record<string, MemberEvidenceResponse>>({});
  const [evidenceLoading, setEvidenceLoading] = useState<Record<string, boolean>>({});

  const [passportLoading, setPassportLoading] = useState<Record<string, boolean>>({});
  const [passportError, setPassportError] = useState<Record<string, string | null>>({});
  const [passportCopied, setPassportCopied] = useState<Record<string, boolean>>({});

  const [disputingMemberId, setDisputingMemberId] = useState<string | null>(null);
  const [disputeText, setDisputeText] = useState("");
  const [disputeSubmitting, setDisputeSubmitting] = useState(false);
  const [disputeError, setDisputeError] = useState<string | null>(null);
  const [disputeSuccess, setDisputeSuccess] = useState<string | null>(null);

  const toggleExpandMember = async (memberId: string) => {
    if (expandedMember === memberId) {
      setExpandedMember(null);
      return;
    }
    setExpandedMember(memberId);
    if (!memberEvidences[memberId]) {
      setEvidenceLoading((prev) => ({ ...prev, [memberId]: true }));
      const ev = await getMemberEvidence(projectId, memberId);
      if (ev) {
        setMemberEvidences((prev) => ({ ...prev, [memberId]: ev }));
      }
      setEvidenceLoading((prev) => ({ ...prev, [memberId]: false }));
    }
  };

  const handlePublish = async (memberId: string) => {
    setPassportLoading((prev) => ({ ...prev, [memberId]: true }));
    setPassportError((prev) => ({ ...prev, [memberId]: null }));
    try {
      const res = await publishPassport(projectId, memberId);
      if (res.ok && res.code && res.url) {
        onPassportPublished?.(memberId, res.code, res.url);
      } else {
        setPassportError((prev) => ({ ...prev, [memberId]: res.error || "Failed to publish passport." }));
      }
    } catch {
      setPassportError((prev) => ({ ...prev, [memberId]: "Network error." }));
    } finally {
      setPassportLoading((prev) => ({ ...prev, [memberId]: false }));
    }
  };

  const handleCopyPassport = (memberId: string, code: string) => {
    const url = `${window.location.origin}/p/${code}`;
    navigator.clipboard.writeText(url);
    setPassportCopied((prev) => ({ ...prev, [memberId]: true }));
    setTimeout(() => {
      setPassportCopied((prev) => ({ ...prev, [memberId]: false }));
    }, 2000);
  };

  const handleSubmitDispute = async (memberId: string) => {
    if (!disputeText.trim()) return;
    setDisputeSubmitting(true);
    setDisputeError(null);
    setDisputeSuccess(null);
    try {
      const res = await createDispute(projectId, memberId, disputeText.trim());
      if (res.ok) {
        setDisputeSuccess("Dispute raised. Project owners and faculty have been notified.");
        setDisputeText("");
        onDisputeSubmitted?.();
        setTimeout(() => {
          setDisputingMemberId(null);
          setDisputeSuccess(null);
        }, 2000);
      } else {
        setDisputeError(res.error || "Failed to submit dispute.");
      }
    } catch {
      setDisputeError("Network error while submitting dispute.");
    } finally {
      setDisputeSubmitting(false);
    }
  };

  const handleReanalyze = async () => {
    await triggerAnalysis(projectId);
    onAnalysisTriggered?.();
  };

  const safeMembers = Array.isArray(scores?.members) ? scores.members : [];
  const projectFlags = Array.isArray(scores?.project_flags) ? scores.project_flags : [];

  return (
    <SectionErrorBoundary title="Contribution Scores">
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[18px] font-semibold text-text tracking-tight">
              Contribution Scores &amp; Attribution
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              Auditable 4-signal weighted contribution model (survival, effective change, module ownership, collaboration).
            </p>
          </div>
          {isOwnerOrAdmin && !readOnly && analysisStatus === "complete" && (
            <button
              type="button"
              onClick={handleReanalyze}
              className="btn-secondary text-[12px] h-[32px] px-3 font-medium"
            >
              Re-run analysis
            </button>
          )}
        </div>

        {/* Polling / Status messages */}
        {analysisStatus === "pending" && (
          <div className="bg-surface border border-border rounded-[6px] p-4 text-center space-y-2">
            <p className="text-sm font-medium text-text">Contribution analysis pending</p>
            <p className="text-xs text-text-muted">
              Analysis will begin once repository collection is complete.
            </p>
          </div>
        )}

        {analysisStatus === "running" && (
          <div className="bg-surface border border-accent/40 rounded-[6px] p-5 text-center space-y-3">
            <p className="text-sm font-semibold text-accent">
              {progressStep || "Computing contribution metrics..."}
            </p>
            <div className="max-w-[360px] mx-auto w-full bg-bg border border-border rounded-[4px] h-3 overflow-hidden">
              {typeof progressPercent === "number" ? (
                <div
                  className="bg-accent h-full transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(5, progressPercent))}%` }}
                />
              ) : (
                <div className="bg-accent h-full w-1/3 animate-pulse" />
              )}
            </div>
            <p className="text-xs text-text-muted">
              Analyzing survival, effective lines, module ownership and collaboration. This page will update automatically.
            </p>
          </div>
        )}

        {analysisStatus === "failed" && (
          <div className="bg-surface border border-danger/40 rounded-[6px] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-danger">Analysis Failed</span>
              {isOwnerOrAdmin && !readOnly && (
                <button
                  type="button"
                  onClick={handleReanalyze}
                  className="btn-primary text-xs h-[28px] px-3"
                >
                  Retry analysis
                </button>
              )}
            </div>
            {analysisError && (
              <p className="text-xs font-mono text-danger bg-danger/5 p-2 rounded border border-danger/20">
                {analysisError}
              </p>
            )}
          </div>
        )}

        {/* Complete State */}
        {analysisStatus === "complete" && scores && (
          <>
            {scores.history_since && (
              <div className="bg-surface border border-border rounded-[4px] px-3 py-2 text-[12px] text-text-muted flex items-center justify-between">
                <span>
                  <strong className="text-text font-medium">History window:</strong> Analyzed commits since {formatDate(scores.history_since)}.
                </span>
                {scores.history_window && (
                  <span className="font-mono text-[11px] text-text-muted border border-border px-1.5 py-0.5 rounded-[2px] bg-bg">
                    {scores.history_window}
                  </span>
                )}
              </div>
            )}

            {typeof scores.stats?.vendored_files_ignored === "number" && (
              <div className="bg-surface border border-border rounded-[4px] px-3 py-2 text-[12px] text-text-muted flex items-center justify-between">
                <span>
                  <strong className="text-text font-medium">Files:</strong> {Number(scores.stats.vendored_files_ignored)} vendored {Number(scores.stats.vendored_files_ignored) === 1 ? "file" : "files"} ignored
                </span>
                {Boolean(scores.stats.ignored_reasons && typeof scores.stats.ignored_reasons === "object") && (
                  <span className="font-mono text-[11px] text-text-muted">
                    {Object.entries(scores.stats.ignored_reasons as Record<string, number>)
                      .filter(([, count]) => typeof count === "number" && count > 0)
                      .map(([reason, count]) => `${reason}: ${count}`)
                      .join(", ")}
                  </span>
                )}
              </div>
            )}

            {scores.timing_stats && (
              <div className="bg-surface border border-border rounded-[4px] px-3 py-2 text-[12px] text-text-muted font-mono flex flex-wrap gap-4 items-center">
                <span className="font-semibold text-text uppercase tracking-wider text-[11px] font-sans">
                  Timings
                </span>
                {Boolean(scores.timing_stats.collection && typeof scores.timing_stats.collection === "object") && (
                  <span>
                    Collection: {Number((scores.timing_stats.collection as Record<string, unknown>).total ?? 0).toFixed(2)}s
                    {(scores.timing_stats.collection as Record<string, unknown>).clone_or_fetch !== undefined
                      ? ` (clone: ${Number((scores.timing_stats.collection as Record<string, unknown>).clone_or_fetch).toFixed(2)}s)`
                      : ""}
                  </span>
                )}
                {Boolean(scores.timing_stats.analysis && typeof scores.timing_stats.analysis === "object") && (
                  <span>
                    Analysis: {Number((scores.timing_stats.analysis as Record<string, unknown>).total ?? 0).toFixed(2)}s
                    {(scores.timing_stats.analysis as Record<string, unknown>).git_blame !== undefined
                      ? ` (blame: ${Number((scores.timing_stats.analysis as Record<string, unknown>).git_blame).toFixed(2)}s)`
                      : ""}
                  </span>
                )}
              </div>
            )}

            {projectFlags.length > 0 && (
              <div className="bg-surface border border-border rounded-[4px] p-3 space-y-1.5 text-[12px]">
                <span className="font-semibold text-text uppercase tracking-wider text-[11px] block text-text-muted">
                  Analysis Notices
                </span>
                {projectFlags.map((f) => (
                  <div key={f.code} className="text-text flex items-start gap-2">
                    <span className="font-mono text-[11px] text-text-muted border border-border px-1.5 py-0.5 rounded-[2px] bg-bg shrink-0">
                      {f.code}
                    </span>
                    <span>{f.message}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border bg-bg/50">
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Contributor
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right w-[110px]">
                        Share
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider w-[180px]">
                        Distribution
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-center w-[100px]">
                        Confidence
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Flags
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                        Details
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {safeMembers.map((m) => {
                      const isOthers = m.member_id === "others";
                      const isExpanded = expandedMember === m.member_id;
                      const ev = memberEvidences[m.member_id];
                      const isEvLoading = evidenceLoading[m.member_id];
                      const memDetail = members.find((x) => x.id === m.member_id);
                      const isCurrentUserRow = Boolean(!isOthers && currentUser && memDetail && memDetail.user_id === currentUser.id);
                      const pInfo = passportData[m.member_id];
                      const pLoading = passportLoading[m.member_id];
                      const pError = passportError[m.member_id];
                      const pCopied = passportCopied[m.member_id];
                      const memberFlags = Array.isArray(m.flags) ? m.flags : [];

                      return (
                        <React.Fragment key={m.member_id}>
                          <tr className="hover:bg-bg/40 transition-colors duration-120">
                            <td className="py-3 px-4">
                              <div className="font-medium text-text text-[13px] leading-tight">
                                {m.display_name || (isOthers ? "Others" : "Member")}
                              </div>
                              {!isOthers && (
                                <div className="font-mono text-[12px] text-text-muted">
                                  {m.github_login ? `@${m.github_login}` : "Unlinked"}
                                </div>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-[13px] font-semibold text-text tabular-nums">
                              {Number(m.share_percent || 0).toFixed(2)}%
                            </td>
                            <td className="py-3 px-4">
                              <div className="w-full bg-bg border border-border h-2.5 rounded-[2px] overflow-hidden">
                                <div
                                  className="bg-accent h-full"
                                  style={{ width: `${Math.min(Math.max(Number(m.share_percent || 0), 0), 100)}%` }}
                                />
                              </div>
                            </td>
                            <td className="py-3 px-4 text-center">
                              {isOthers ? (
                                <span className="text-[12px] text-text-muted">—</span>
                              ) : (
                                <span className="font-mono text-[11px] border border-border px-2 py-0.5 rounded-[4px] capitalize text-text">
                                  {m.confidence || "unknown"}
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-4">
                              {isOthers ? (
                                <span className="text-[12px] text-text-muted">—</span>
                              ) : (
                                <div className="flex flex-wrap gap-1">
                                  {memberFlags.length > 0 ? (
                                    memberFlags.map((fl) => (
                                      <span
                                        key={fl}
                                        className="font-mono text-[11px] border border-border px-1.5 py-0.5 rounded-[3px] text-text-muted"
                                      >
                                        {fl}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="text-[12px] text-text-muted">—</span>
                                  )}
                                </div>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right">
                              {isOthers ? (
                                <span className="text-[12px] text-text-muted">—</span>
                              ) : (
                                <div className="flex items-center justify-end gap-1.5 flex-wrap">
                                  <button
                                    type="button"
                                    onClick={() => toggleExpandMember(m.member_id)}
                                    className="btn-secondary text-[12px] h-[28px] px-2.5"
                                  >
                                    {isExpanded ? "Hide breakdown" : "Why this score?"}
                                  </button>
                                  {isCurrentUserRow && !readOnly && (
                                    <>
                                      {pInfo ? (
                                        <>
                                          <a
                                            href={`/p/${pInfo.code}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="btn-secondary text-[12px] h-[28px] px-2.5 inline-flex items-center text-accent"
                                          >
                                            View passport
                                          </a>
                                          <button
                                            type="button"
                                            onClick={() => handleCopyPassport(m.member_id, pInfo.code)}
                                            className="btn-secondary text-[12px] h-[28px] px-2.5"
                                          >
                                            {pCopied ? "Copied" : "Copy link"}
                                          </button>
                                        </>
                                      ) : (
                                        <button
                                          type="button"
                                          onClick={() => handlePublish(m.member_id)}
                                          disabled={pLoading}
                                          className="btn-primary text-[12px] h-[28px] px-2.5"
                                        >
                                          {pLoading ? "Publishing..." : "Publish passport"}
                                        </button>
                                      )}
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setDisputingMemberId(disputingMemberId === m.member_id ? null : m.member_id);
                                          setDisputeError(null);
                                          setDisputeSuccess(null);
                                        }}
                                        className="btn-secondary text-[12px] h-[28px] px-2.5"
                                      >
                                        {disputingMemberId === m.member_id ? "Cancel dispute" : "Dispute this score"}
                                      </button>
                                    </>
                                  )}
                                  {pError && (
                                    <div className="text-[11px] text-danger mt-1 text-right">{pError}</div>
                                  )}
                                </div>
                              )}
                            </td>
                          </tr>

                          {/* Inline Dispute Form */}
                          {disputingMemberId === m.member_id && (
                            <tr className="bg-bg/40">
                              <td colSpan={6} className="p-4 border-b border-border">
                                <div className="max-w-xl space-y-2">
                                  <div className="flex justify-between items-center">
                                    <label className="text-[12px] font-semibold text-text uppercase tracking-wider text-text-muted">
                                      Dispute this contribution score
                                    </label>
                                    <span className="font-mono text-[11px] text-text-muted tabular-nums">
                                      {1000 - disputeText.length} characters remaining
                                    </span>
                                  </div>
                                  <textarea
                                    value={disputeText}
                                    onChange={(e) => setDisputeText(e.target.value)}
                                    maxLength={1000}
                                    rows={3}
                                    placeholder="Describe why this score or attribution may be inaccurate..."
                                    className="w-full text-[13px] bg-surface border border-border rounded-[4px] p-2 text-text focus:outline-none focus:ring-1 focus:ring-accent"
                                  />
                                  {disputeError && (
                                    <div className="text-[12px] text-danger">{disputeError}</div>
                                  )}
                                  {disputeSuccess && (
                                    <div className="text-[12px] text-success">{disputeSuccess}</div>
                                  )}
                                  <div className="flex gap-2 pt-1">
                                    <button
                                      type="button"
                                      onClick={() => handleSubmitDispute(m.member_id)}
                                      disabled={disputeSubmitting || !disputeText.trim()}
                                      className="btn-primary text-[12px] h-[30px] px-3 disabled:opacity-50"
                                    >
                                      {disputeSubmitting ? "Submitting..." : "Submit dispute"}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setDisputingMemberId(null);
                                        setDisputeError(null);
                                        setDisputeSuccess(null);
                                      }}
                                      className="btn-secondary text-[12px] h-[30px] px-3"
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}

                          {/* Expanded Evidence Breakdown */}
                          {isExpanded && (
                            <tr className="bg-bg/25">
                              <td colSpan={6} className="p-4 border-b border-border">
                                {isEvLoading ? (
                                  <p className="text-text-muted text-[12px] font-mono">Loading evidence...</p>
                                ) : ev ? (
                                  <div className="space-y-4 text-[13px] text-text">
                                    <div className="p-3 bg-surface border border-border rounded-[4px] font-medium text-text">
                                      {ev.summary_sentence || "Summary not available."}
                                    </div>

                                    {/* Signal Breakdown */}
                                    {ev.signals && (
                                      <div>
                                        <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-2 text-text-muted">
                                          Signal Breakdown
                                        </h4>
                                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                          <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                            <div className="text-[11px] text-text-muted uppercase">Survival ({Math.round((ev.signals.survival?.weight || 0) * 100)}%)</div>
                                            <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                              {Math.round(ev.signals.survival?.raw || 0)} lines
                                            </div>
                                            <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                              Share: {((ev.signals.survival?.normalized || 0) * 100).toFixed(1)}%
                                            </div>
                                          </div>
                                          <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                            <div className="text-[11px] text-text-muted uppercase">Effective Change ({Math.round((ev.signals.effective_change?.weight || 0) * 100)}%)</div>
                                            <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                              {Math.round(ev.signals.effective_change?.raw || 0)} lines
                                            </div>
                                            <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                              Share: {((ev.signals.effective_change?.normalized || 0) * 100).toFixed(1)}%
                                            </div>
                                          </div>
                                          <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                            <div className="text-[11px] text-text-muted uppercase">Ownership ({Math.round((ev.signals.ownership?.weight || 0) * 100)}%)</div>
                                            <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                              {((ev.signals.ownership?.normalized || 0) * 100).toFixed(1)}%
                                            </div>
                                            <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                              {Array.isArray(ev.owned_modules) ? ev.owned_modules.length : 0} owned module(s)
                                            </div>
                                          </div>
                                          <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                            <div className="text-[11px] text-text-muted uppercase">Collaboration ({Math.round((ev.signals.collaboration?.weight || 0) * 100)}%)</div>
                                            <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                              {Number(ev.signals.collaboration?.raw || 0).toFixed(1)} pts
                                            </div>
                                            <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                              Share: {((ev.signals.collaboration?.normalized || 0) * 100).toFixed(1)}%
                                            </div>
                                          </div>
                                        </div>
                                      </div>
                                    )}

                                    {/* Owned Modules */}
                                    {Array.isArray(ev.owned_modules) && ev.owned_modules.length > 0 && (
                                      <div>
                                        <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-1.5 text-text-muted">
                                          Owned Modules
                                        </h4>
                                        <div className="flex flex-wrap gap-2">
                                          {ev.owned_modules.map((om, omIdx) => {
                                            const modObj = om as { path?: string; module?: string; share?: number };
                                            const modPath = modObj.path || modObj.module || "module";
                                            return (
                                              <span key={om.path || omIdx} className="font-mono text-[12px] border border-border bg-surface px-2 py-0.5 rounded-[4px]">
                                                {modPath} <span className="text-text-muted">({(Number(om.share || 0) * 100).toFixed(1)}% lead)</span>
                                              </span>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    )}

                                    {/* Top Commits & Files Grid */}
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <div>
                                        <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-1.5 text-text-muted">
                                          Top Commits by Impact
                                        </h4>
                                        {!Array.isArray(ev.top_commits) || ev.top_commits.length === 0 ? (
                                          <p className="text-[12px] text-text-muted">No counted commits</p>
                                        ) : (
                                          <div className="space-y-1">
                                            {ev.top_commits.map((tc, tcIdx) => {
                                              const shaShort = typeof tc.sha === "string" && tc.sha.length >= 7 ? tc.sha.slice(0, 7) : (tc.sha || "—");
                                              return (
                                                <div key={tc.sha || tcIdx} className="text-[12px] flex items-center justify-between gap-2 p-1.5 bg-surface border border-border rounded-[4px]">
                                                  <div className="truncate flex items-center gap-1.5">
                                                    {tc.commit_url ? (
                                                      <a
                                                        href={tc.commit_url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="font-mono text-accent hover:underline"
                                                      >
                                                        {shaShort}
                                                      </a>
                                                    ) : (
                                                      <span className="font-mono text-text">{shaShort}</span>
                                                    )}
                                                    <span className="truncate text-text">{tc.subject || "Commit"}</span>
                                                  </div>
                                                  <span className="font-mono text-text-muted text-[11px] tabular-nums whitespace-nowrap">
                                                    +{tc.effective_lines}
                                                  </span>
                                                </div>
                                              );
                                            })}
                                          </div>
                                        )}
                                      </div>

                                      <div>
                                        <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-1.5 text-text-muted">
                                          Top Files by Surviving Code
                                        </h4>
                                        {!Array.isArray(ev.top_files) || ev.top_files.length === 0 ? (
                                          <p className="text-[12px] text-text-muted">No surviving files</p>
                                        ) : (
                                          <div className="space-y-1">
                                            {ev.top_files.map((tf, tfIdx) => (
                                              <div key={tf.path || tfIdx} className="text-[12px] flex items-center justify-between gap-2 p-1.5 bg-surface border border-border rounded-[4px]">
                                                <span className="font-mono truncate text-text">{tf.path}</span>
                                                <span className="font-mono text-text-muted text-[11px] tabular-nums whitespace-nowrap">
                                                  {tf.surviving_lines} lines
                                                </span>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ) : (
                                  <p className="text-text-muted text-[12px]">Failed to load evidence breakdown.</p>
                                )}
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </section>
    </SectionErrorBoundary>
  );
}
