"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ProjectDetail,
  MemberDetail,
  UnlinkedAlias,
  CommitItem,
  ProjectScoresResponse,
  MemberEvidenceResponse,
  getProjectDetail,
  getProjectMembers,
  getProjectUnlinkedAliases,
  getProjectCommits,
  recollectProject,
  deleteProject,
  assignAlias,
  mergeMembers,
  getProjectScores,
  getMemberEvidence,
  getAnalysisStatus,
  triggerAnalysis,
} from "@/lib/api";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [members, setMembers] = useState<MemberDetail[]>([]);
  const [unlinkedAliases, setUnlinkedAliases] = useState<UnlinkedAlias[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [scores, setScores] = useState<ProjectScoresResponse | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<string>("pending");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [expandedMember, setExpandedMember] = useState<string | null>(null);
  const [memberEvidences, setMemberEvidences] = useState<Record<string, MemberEvidenceResponse>>({});
  const [evidenceLoading, setEvidenceLoading] = useState<Record<string, boolean>>({});

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Assignment & Merge state
  const [selectedMemberForAlias, setSelectedMemberForAlias] = useState<Record<string, string>>({});
  const [mergeSource, setMergeSource] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");
  const [confirmMerge, setConfirmMerge] = useState(false);

  const loadData = useCallback(async () => {
    if (!id) return;
    const proj = await getProjectDetail(id);
    if (!proj) {
      router.push("/");
      return;
    }
    setProject(proj);

    if (proj.status === "ready") {
      const [mems, aliases, cms, statusRes, scoreRes] = await Promise.all([
        getProjectMembers(id),
        getProjectUnlinkedAliases(id),
        getProjectCommits(id, 50, 0),
        getAnalysisStatus(id),
        getProjectScores(id),
      ]);
      setMembers(mems);
      setUnlinkedAliases(aliases);
      setCommits(cms);
      if (statusRes) {
        setAnalysisStatus(statusRes.analysis_status);
        setAnalysisError(statusRes.analysis_error);
      }
      if (scoreRes) {
        setScores(scoreRes);
      }
    }
    setLoading(false);
  }, [id, router]);

  useEffect(() => {
    async function fetchData() {
      if (!id) return;
      await loadData();
    }

    void fetchData();
  }, [id, loadData]);

  // Polling while collection or analysis is running
  useEffect(() => {
    const isCollecting = project && (project.status === "pending" || project.status === "analyzing");
    const isAnalyzing = analysisStatus === "running";

    if (!isCollecting && !isAnalyzing) {
      return;
    }

    const interval = setInterval(async () => {
      if (isCollecting) {
        const updated = await getProjectDetail(id);
        if (updated) {
          setProject(updated);
          if (updated.status === "ready") {
            const [mems, aliases, cms, statusRes, scoreRes] = await Promise.all([
              getProjectMembers(id),
              getProjectUnlinkedAliases(id),
              getProjectCommits(id, 50, 0),
              getAnalysisStatus(id),
              getProjectScores(id),
            ]);
            setMembers(mems);
            setUnlinkedAliases(aliases);
            setCommits(cms);
            if (statusRes) {
              setAnalysisStatus(statusRes.analysis_status);
              setAnalysisError(statusRes.analysis_error);
            }
            if (scoreRes) {
              setScores(scoreRes);
            }
          }
        }
      } else if (isAnalyzing) {
        const statusRes = await getAnalysisStatus(id);
        if (statusRes) {
          setAnalysisStatus(statusRes.analysis_status);
          setAnalysisError(statusRes.analysis_error);
          if (statusRes.analysis_status === "complete") {
            const scoreRes = await getProjectScores(id);
            if (scoreRes) {
              setScores(scoreRes);
            }
          }
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [id, project, analysisStatus]);

  const handleRecollect = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    await recollectProject(id);
    await loadData();
    setActionLoading(false);
  };

  const handleReanalyze = async () => {
    if (actionLoading || analysisStatus === "running") return;
    setActionLoading(true);
    setAnalysisStatus("running");
    await triggerAnalysis(id);
    setActionLoading(false);
  };

  const toggleExpandMember = async (memberId: string) => {
    if (expandedMember === memberId) {
      setExpandedMember(null);
      return;
    }
    setExpandedMember(memberId);
    if (!memberEvidences[memberId]) {
      setEvidenceLoading((prev) => ({ ...prev, [memberId]: true }));
      const ev = await getMemberEvidence(id, memberId);
      if (ev) {
        setMemberEvidences((prev) => ({ ...prev, [memberId]: ev }));
      }
      setEvidenceLoading((prev) => ({ ...prev, [memberId]: false }));
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setActionLoading(true);
    const ok = await deleteProject(id);
    if (ok) {
      router.push("/dashboard");
    } else {
      setActionLoading(false);
      setConfirmDelete(false);
    }
  };

  const handleAssign = async (aliasId: string) => {
    const targetMemberId = selectedMemberForAlias[aliasId];
    if (!targetMemberId) return;
    setActionLoading(true);
    await assignAlias(id, aliasId, targetMemberId);
    await loadData();
    setActionLoading(false);
  };

  const handleMerge = async () => {
    if (!mergeSource || !mergeTarget || mergeSource === mergeTarget) return;
    if (!confirmMerge) {
      setConfirmMerge(true);
      return;
    }
    setActionLoading(true);
    await mergeMembers(id, mergeSource, targetMemberIdClean(mergeTarget));
    setMergeSource("");
    setMergeTarget("");
    setConfirmMerge(false);
    await loadData();
    setActionLoading(false);
  };

  const targetMemberIdClean = (val: string) => val;

  if (loading || !project) {
    return (
      <div className="min-h-full flex flex-col bg-bg">
        <header className="w-full h-[56px] border-b border-border bg-surface">
          <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
            <Link href="/dashboard" className="font-serif text-[18px] font-semibold text-text tracking-tight">
              Provenance
            </Link>
          </div>
        </header>
        <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-8">
          <p className="text-text-muted text-sm">Loading project...</p>
        </main>
      </div>
    );
  }

  const lastCollectedStr = project.last_collected_at
    ? new Date(project.last_collected_at).toISOString().replace("T", " ").replace(/\..+/, " UTC")
    : "—";

  return (
    <div className="min-h-full flex flex-col bg-bg">
      <header className="w-full h-[56px] border-b border-border bg-surface">
        <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
          <Link href="/dashboard" className="font-serif text-[18px] font-semibold text-text tracking-tight">
            Provenance
          </Link>
          <Link href="/dashboard" className="text-sm text-text-muted hover:text-text">
            Back to dashboard
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-8 space-y-6">
        {/* Project Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-mono text-[20px] font-semibold text-text tracking-tight">
                {project.repo_full_name}
              </h1>
              <span className="font-mono text-[12px] border border-border px-2 py-0.5 rounded-[4px] bg-surface capitalize text-text">
                {project.status}
              </span>
              {project.is_private && (
                <span className="text-[11px] font-mono border border-border px-1.5 py-0.5 rounded-[3px] text-text-muted">
                  private
                </span>
              )}
            </div>
            {project.description && (
              <p className="text-[13px] text-text-muted mt-1">{project.description}</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRecollect}
              disabled={actionLoading || project.status === "analyzing"}
              className="btn-secondary text-[13px]"
            >
              Re-run collection
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={actionLoading}
              className={`btn-secondary text-[13px] ${confirmDelete ? "border-danger text-danger" : ""}`}
            >
              {confirmDelete ? "Confirm delete" : "Delete project"}
            </button>
          </div>
        </div>

        {/* Warnings notice block */}
        {project.warnings && (
          <div className="bg-surface border border-warning rounded-[4px] p-3 text-[13px] text-text">
            <span className="font-medium text-warning mr-1">Notice:</span>
            {project.warnings}
          </div>
        )}

        {/* Pending / Analyzing State */}
        {(project.status === "pending" || project.status === "analyzing") && (
          <div className="bg-surface border border-border rounded-[6px] p-8 text-center">
            <p className="text-text font-medium text-[15px] mb-2">
              Collecting repository history...
            </p>
            <p className="text-text-muted text-[13px]">
              Cloning repository history and mapping author identities. This page will update automatically.
            </p>
          </div>
        )}

        {/* Failed State */}
        {project.status === "failed" && (
          <div className="bg-surface border border-danger rounded-[6px] p-6">
            <h2 className="text-danger font-medium text-[15px] mb-2">Collection failed</h2>
            <p className="text-text text-[13px] mb-4">
              {project.error_message || "An error occurred during repository analysis."}
            </p>
            <button
              type="button"
              onClick={handleRecollect}
              disabled={actionLoading}
              className="btn-primary text-[13px]"
            >
              Retry collection
            </button>
          </div>
        )}

        {/* Ready State */}
        {project.status === "ready" && (
          <>
            {/* 1) Summary Line */}
            <div className="bg-surface border border-border rounded-[6px] px-4 py-3 text-[13px] text-text font-mono flex flex-wrap gap-4 items-center">
              <span>
                <strong className="font-semibold text-text">{project.commit_total.toLocaleString()}</strong> commits
              </span>
              <span className="text-border-strong">•</span>
              <span>
                <strong className="font-semibold text-text">{members.length}</strong> members
              </span>
              <span className="text-border-strong">•</span>
              <span>
                <strong className="font-semibold text-text">{project.prs_count}</strong> pull requests
              </span>
              <span className="text-border-strong">•</span>
              <span className="text-text-muted">
                Last collected: <span className="tabular-nums text-text">{lastCollectedStr}</span>
              </span>
            </div>

            {/* 1.5) Contribution Scores Section */}
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
                  Contribution Scores
                </h2>
                {analysisStatus !== "running" && (
                  <button
                    type="button"
                    onClick={handleReanalyze}
                    disabled={actionLoading}
                    className="btn-secondary text-[12px] h-[30px] px-2.5"
                  >
                    Re-run analysis
                  </button>
                )}
              </div>

              {/* While analysis is running */}
              {analysisStatus === "running" && (
                <div className="bg-surface border border-border rounded-[6px] p-6 text-center">
                  <p className="text-text font-medium text-[14px] mb-1">
                    Analyzing contributions...
                  </p>
                  <p className="text-text-muted text-[12px]">
                    Computing survival, effective lines, module ownership and collaboration. This page will update automatically.
                  </p>
                </div>
              )}

              {/* If analysis failed */}
              {analysisStatus === "failed" && (
                <div className="bg-surface border border-danger rounded-[6px] p-4 text-[13px]">
                  <p className="text-danger font-medium mb-1">Analysis failed</p>
                  <p className="text-text-muted mb-3">{analysisError || "An error occurred during scoring."}</p>
                  <button
                    type="button"
                    onClick={handleReanalyze}
                    disabled={actionLoading}
                    className="btn-primary text-[12px] h-[30px]"
                  >
                    Retry analysis
                  </button>
                </div>
              )}

              {/* If complete */}
              {analysisStatus === "complete" && scores && (
                <>
                  {/* Notice block for project-level flags */}
                  {scores.project_flags && scores.project_flags.length > 0 && (
                    <div className="bg-surface border border-border rounded-[4px] p-3 space-y-1.5 text-[12px]">
                      <span className="font-semibold text-text uppercase tracking-wider text-[11px] block text-text-muted">
                        Analysis Notices
                      </span>
                      {scores.project_flags.map((f) => (
                        <div key={f.code} className="text-text flex items-start gap-2">
                          <span className="font-mono text-[11px] text-text-muted border border-border px-1.5 py-0.5 rounded-[2px] bg-bg shrink-0">
                            {f.code}
                          </span>
                          <span>{f.message}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Scores Table */}
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
                          {scores.members.map((m) => {
                            const isExpanded = expandedMember === m.member_id;
                            const ev = memberEvidences[m.member_id];
                            const isEvLoading = evidenceLoading[m.member_id];

                            return (
                              <React.Fragment key={m.member_id}>
                                <tr className="hover:bg-bg/40 transition-colors duration-120">
                                  <td className="py-3 px-4">
                                    {m.display_name && (
                                      <div className="font-medium text-text text-[13px] leading-tight">
                                        {m.display_name}
                                      </div>
                                    )}
                                    <div className="font-mono text-[12px] text-text-muted">
                                      {m.github_login ? `@${m.github_login}` : "Unlinked"}
                                    </div>
                                  </td>
                                  <td className="py-3 px-4 text-right font-mono text-[13px] font-semibold text-text tabular-nums">
                                    {m.share_percent.toFixed(2)}%
                                  </td>
                                  <td className="py-3 px-4">
                                    <div className="w-full bg-bg border border-border h-2.5 rounded-[2px] overflow-hidden">
                                      <div
                                        className="bg-accent h-full"
                                        style={{ width: `${Math.min(Math.max(m.share_percent, 0), 100)}%` }}
                                      />
                                    </div>
                                  </td>
                                  <td className="py-3 px-4 text-center">
                                    <span className="font-mono text-[11px] border border-border px-2 py-0.5 rounded-[4px] capitalize text-text">
                                      {m.confidence}
                                    </span>
                                  </td>
                                  <td className="py-3 px-4">
                                    <div className="flex flex-wrap gap-1">
                                      {m.flags.length > 0 ? (
                                        m.flags.map((fl) => (
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
                                  </td>
                                  <td className="py-3 px-4 text-right">
                                    <button
                                      type="button"
                                      onClick={() => toggleExpandMember(m.member_id)}
                                      className="btn-secondary text-[12px] h-[28px] px-2.5"
                                    >
                                      {isExpanded ? "Hide breakdown" : "Why this score?"}
                                    </button>
                                  </td>
                                </tr>

                                {/* Expanded Evidence Breakdown */}
                                {isExpanded && (
                                  <tr className="bg-bg/25">
                                    <td colSpan={6} className="p-4 border-b border-border">
                                      {isEvLoading ? (
                                        <p className="text-text-muted text-[12px] font-mono">Loading evidence...</p>
                                      ) : ev ? (
                                        <div className="space-y-4 text-[13px] text-text">
                                          {/* Plain summary sentence */}
                                          <div className="p-3 bg-surface border border-border rounded-[4px] font-medium text-text">
                                            {ev.summary_sentence}
                                          </div>

                                          {/* Signal Breakdown */}
                                          <div>
                                            <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-2 text-text-muted">
                                              Signal Breakdown
                                            </h4>
                                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                              <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                                <div className="text-[11px] text-text-muted uppercase">Survival ({Math.round(ev.signals.survival.weight * 100)}%)</div>
                                                <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                                  {Math.round(ev.signals.survival.raw)} lines
                                                </div>
                                                <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                                  Share: {(ev.signals.survival.normalized * 100).toFixed(1)}%
                                                </div>
                                              </div>
                                              <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                                <div className="text-[11px] text-text-muted uppercase">Effective Change ({Math.round(ev.signals.effective_change.weight * 100)}%)</div>
                                                <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                                  {Math.round(ev.signals.effective_change.raw)} lines
                                                </div>
                                                <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                                  Share: {(ev.signals.effective_change.normalized * 100).toFixed(1)}%
                                                </div>
                                              </div>
                                              <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                                <div className="text-[11px] text-text-muted uppercase">Ownership ({Math.round(ev.signals.ownership.weight * 100)}%)</div>
                                                <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                                  {(ev.signals.ownership.normalized * 100).toFixed(1)}%
                                                </div>
                                                <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                                  {ev.owned_modules.length} owned module(s)
                                                </div>
                                              </div>
                                              <div className="p-2.5 bg-surface border border-border rounded-[4px]">
                                                <div className="text-[11px] text-text-muted uppercase">Collaboration ({Math.round(ev.signals.collaboration.weight * 100)}%)</div>
                                                <div className="font-mono text-[14px] font-semibold text-text tabular-nums mt-0.5">
                                                  {ev.signals.collaboration.raw.toFixed(1)} pts
                                                </div>
                                                <div className="font-mono text-[11px] text-text-muted mt-0.5">
                                                  Share: {(ev.signals.collaboration.normalized * 100).toFixed(1)}%
                                                </div>
                                              </div>
                                            </div>
                                          </div>

                                          {/* Owned Modules */}
                                          {ev.owned_modules.length > 0 && (
                                            <div>
                                              <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-1.5 text-text-muted">
                                                Owned Modules
                                              </h4>
                                              <div className="flex flex-wrap gap-2">
                                                {ev.owned_modules.map((om) => (
                                                  <span key={om.path} className="font-mono text-[12px] border border-border bg-surface px-2 py-0.5 rounded-[4px]">
                                                    {om.path} <span className="text-text-muted">({(om.share * 100).toFixed(1)}% lead)</span>
                                                  </span>
                                                ))}
                                              </div>
                                            </div>
                                          )}

                                          {/* Top Commits & Files Grid */}
                                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div>
                                              <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-1.5 text-text-muted">
                                                Top Commits by Impact
                                              </h4>
                                              {ev.top_commits.length === 0 ? (
                                                <p className="text-[12px] text-text-muted">No counted commits</p>
                                              ) : (
                                                <div className="space-y-1">
                                                  {ev.top_commits.map((tc) => (
                                                    <div key={tc.sha} className="text-[12px] flex items-center justify-between gap-2 p-1.5 bg-surface border border-border rounded-[4px]">
                                                      <div className="truncate flex items-center gap-1.5">
                                                        {tc.commit_url ? (
                                                          <a
                                                            href={tc.commit_url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="font-mono text-accent hover:underline"
                                                          >
                                                            {tc.sha.slice(0, 7)}
                                                          </a>
                                                        ) : (
                                                          <span className="font-mono text-text">{tc.sha.slice(0, 7)}</span>
                                                        )}
                                                        <span className="truncate text-text">{tc.subject}</span>
                                                      </div>
                                                      <span className="font-mono text-text-muted text-[11px] tabular-nums whitespace-nowrap">
                                                        +{tc.effective_lines}
                                                      </span>
                                                    </div>
                                                  ))}
                                                </div>
                                              )}
                                            </div>

                                            <div>
                                              <h4 className="text-[12px] font-semibold text-text uppercase tracking-wider mb-1.5 text-text-muted">
                                                Top Files by Surviving Code
                                              </h4>
                                              {ev.top_files.length === 0 ? (
                                                <p className="text-[12px] text-text-muted">No surviving files</p>
                                              ) : (
                                                <div className="space-y-1">
                                                  {ev.top_files.map((tf) => (
                                                    <div key={tf.path} className="text-[12px] flex items-center justify-between gap-2 p-1.5 bg-surface border border-border rounded-[4px]">
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

                  {/* Footer line */}
                  <div className="text-[12px] text-text-muted font-mono pt-1">
                    Scoring version {scores.scoring_version}. Weights: survival {Math.round((scores.weights.survival ?? 0.4) * 100)}%, effective change {Math.round((scores.weights.effective_change ?? 0.25) * 100)}%, ownership {Math.round((scores.weights.ownership ?? 0.15) * 100)}%, collaboration {Math.round((scores.weights.collaboration ?? 0.2) * 100)}%.
                  </div>
                </>
              )}
            </section>

            {/* 2) Members Table */}
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
                      {members.map((m) => {
                        const firstStr = m.first_commit_at
                          ? new Date(m.first_commit_at).toISOString().slice(0, 10)
                          : "—";
                        const lastStr = m.last_commit_at
                          ? new Date(m.last_commit_at).toISOString().slice(0, 10)
                          : "—";

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
                              {m.commit_count.toLocaleString()}
                            </td>
                            <td className="py-2.5 px-4 text-right tabular-nums text-success">
                              +{m.additions.toLocaleString()}
                            </td>
                            <td className="py-2.5 px-4 text-right tabular-nums text-danger">
                              -{m.deletions.toLocaleString()}
                            </td>
                            <td className="py-2.5 px-4 text-right tabular-nums text-text">
                              {m.pull_requests_opened}
                            </td>
                            <td className="py-2.5 px-4 text-right tabular-nums text-text">
                              {m.reviews_given}
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
                      {members.length === 0 && (
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

            {/* 3) Unlinked Identities & Merge Controls */}
            {unlinkedAliases.length > 0 && (
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
                          <th className="py-2 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                            Assign to member
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border font-mono text-[13px]">
                        {unlinkedAliases.map((a) => (
                          <tr key={a.id} className="hover:bg-bg/40 transition-colors duration-120">
                            <td className="py-2 px-4 text-text">{a.name}</td>
                            <td className="py-2 px-4 text-text-muted">{a.email}</td>
                            <td className="py-2 px-4 text-right tabular-nums text-text">
                              {a.commit_count}
                            </td>
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
                                  {members.map((m) => (
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
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Merge Members Control for Owners */}
                {members.length > 1 && (
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
                          {members.map((m) => (
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
                          {members.map((m) => (
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

            {/* 4) Recent Commits */}
            <section className="space-y-3">
              <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
                Recent commits
              </h2>
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
                      {commits.map((c) => {
                        const dateStr = c.authored_at
                          ? new Date(c.authored_at).toISOString().replace("T", " ").replace(/\..+/, "")
                          : "—";

                        return (
                          <tr key={c.id} className="hover:bg-bg/40 transition-colors duration-120">
                            <td className="py-2 px-4 font-mono font-medium text-accent">
                              {c.sha.slice(0, 7)}
                            </td>
                            <td className="py-2 px-4 text-text">{c.author_name}</td>
                            <td className="py-2 px-4 font-mono text-text-muted tabular-nums">
                              {dateStr}
                            </td>
                            <td className="py-2 px-4 text-text truncate max-w-[400px]">
                              {c.subject}
                            </td>
                          </tr>
                        );
                      })}
                      {commits.length === 0 && (
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
          </>
        )}
      </main>
    </div>
  );
}
