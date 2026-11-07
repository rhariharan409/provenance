"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ProjectDetail,
  MemberDetail,
  UnlinkedAlias,
  CommitItem,
  getProjectDetail,
  getProjectMembers,
  getProjectUnlinkedAliases,
  getProjectCommits,
  recollectProject,
  deleteProject,
  assignAlias,
  mergeMembers,
} from "@/lib/api";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [members, setMembers] = useState<MemberDetail[]>([]);
  const [unlinkedAliases, setUnlinkedAliases] = useState<UnlinkedAlias[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
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
      const [mems, aliases, cms] = await Promise.all([
        getProjectMembers(id),
        getProjectUnlinkedAliases(id),
        getProjectCommits(id, 50, 0),
      ]);
      setMembers(mems);
      setUnlinkedAliases(aliases);
      setCommits(cms);
    }
    setLoading(false);
  }, [id, router]);

  useEffect(() => {
    let active = true;

    async function fetchData() {
      if (!id) return;
      const proj = await getProjectDetail(id);
      if (!active) return;
      if (!proj) {
        router.push("/");
        return;
      }
      setProject(proj);

      if (proj.status === "ready") {
        const [mems, aliases, cms] = await Promise.all([
          getProjectMembers(id),
          getProjectUnlinkedAliases(id),
          getProjectCommits(id, 50, 0),
        ]);
        if (!active) return;
        setMembers(mems);
        setUnlinkedAliases(aliases);
        setCommits(cms);
      }
      setLoading(false);
    }

    void fetchData();

    return () => {
      active = false;
    };
  }, [id, router]);

  // Polling while pending or analyzing
  useEffect(() => {
    if (!project || (project.status !== "pending" && project.status !== "analyzing")) {
      return;
    }

    const interval = setInterval(async () => {
      const updated = await getProjectDetail(id);
      if (updated) {
        setProject(updated);
        if (updated.status === "ready") {
          const [mems, aliases, cms] = await Promise.all([
            getProjectMembers(id),
            getProjectUnlinkedAliases(id),
            getProjectCommits(id, 50, 0),
          ]);
          setMembers(mems);
          setUnlinkedAliases(aliases);
          setCommits(cms);
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [id, project]);

  const handleRecollect = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    await recollectProject(id);
    await loadData();
    setActionLoading(false);
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
