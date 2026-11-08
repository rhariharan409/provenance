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
  UserProfile,
  DisputeItem,
  ProjectReviewerItem,
  MemberSummaryItem,
  OriginalityResponse,
  getProjectDetail,
  getProjectMembers,
  getProjectUnlinkedAliases,
  getProjectCommits,
  recollectProject,
  deleteProject,
  getProjectScores,
  getAnalysisStatus,
  getCurrentUserClient,
  getMyPassports,
  listDisputes,
  getProjectReviewers,
  getProjectSummaries,
  getOriginalityMatches,
} from "@/lib/api";
import ProjectHeader from "@/components/ProjectHeader";
import ScoresTable from "@/components/ScoresTable";
import MembersTable from "@/components/MembersTable";
import UnlinkedIdentities from "@/components/UnlinkedIdentities";
import RecentCommits from "@/components/RecentCommits";
import DisputesPanel from "@/components/DisputesPanel";
import CollapsiblePanel from "@/components/CollapsiblePanel";
import ReviewersPanel from "@/components/ReviewersPanel";
import SummariesPanel from "@/components/SummariesPanel";
import OriginalityPanel from "@/components/OriginalityPanel";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [members, setMembers] = useState<MemberDetail[]>([]);
  const [unlinkedAliases, setUnlinkedAliases] = useState<UnlinkedAlias[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [scores, setScores] = useState<ProjectScoresResponse | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<string>("pending");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [progressStep, setProgressStep] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState<number | null>(null);

  // Passport state
  const [passportData, setPassportData] = useState<Record<string, { code: string; url: string }>>({});

  // Disputes list
  const [disputes, setDisputes] = useState<DisputeItem[]>([]);

  // Reviewers list
  const [reviewersList, setReviewersList] = useState<ProjectReviewerItem[]>([]);

  // Summaries
  const [summaries, setSummaries] = useState<MemberSummaryItem[]>([]);

  // Originality
  const [originalityResponse, setOriginalityResponse] = useState<OriginalityResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isOwnerOrAdmin = Boolean(currentUser && project && (project.owner_id === currentUser.id || currentUser.role === "admin"));
  const isAssignedFaculty = Boolean(
    currentUser &&
      (currentUser.role === "faculty" ||
        reviewersList.some(
          (f) =>
            f.status === "accepted" &&
            ("user_id" in f ? (f as { user_id?: string }).user_id === currentUser.id : f.invitee_username.toLowerCase() === currentUser.username.toLowerCase())
        ))
  );
  const canExport = isOwnerOrAdmin || isAssignedFaculty;

  const loadData = useCallback(async () => {
    if (!id) return;
    const [userProfile, proj] = await Promise.all([
      getCurrentUserClient(),
      getProjectDetail(id),
    ]);
    if (userProfile) {
      setCurrentUser(userProfile);
    }
    if (!proj) {
      router.push("/");
      return;
    }
    setProject(proj);
    if (proj.progress_step !== undefined) setProgressStep(proj.progress_step);
    if (proj.progress_percent !== undefined) setProgressPercent(proj.progress_percent);

    if (proj.status === "ready") {
      const [mems, aliases, cms, statusRes, scoreRes, dispList, myPassports, revList, sums, orig] = await Promise.all([
        getProjectMembers(id),
        getProjectUnlinkedAliases(id),
        getProjectCommits(id, 50, 0),
        getAnalysisStatus(id),
        getProjectScores(id),
        listDisputes(id),
        getMyPassports(),
        getProjectReviewers(id),
        getProjectSummaries(id),
        getOriginalityMatches(id),
      ]);
      setMembers(Array.isArray(mems) ? mems : []);
      setUnlinkedAliases(Array.isArray(aliases) ? aliases : []);
      setCommits(Array.isArray(cms) ? cms : []);
      setDisputes(Array.isArray(dispList) ? dispList : []);
      setReviewersList(Array.isArray(revList) ? revList : []);
      setSummaries(Array.isArray(sums) ? sums : []);
      setOriginalityResponse(orig);

      if (Array.isArray(myPassports) && myPassports.length > 0) {
        const initialPassports: Record<string, { code: string; url: string }> = {};
        for (const p of myPassports) {
          if (p.project_id === id && p.status === "active" && p.member_id) {
            initialPassports[p.member_id] = { code: p.code, url: p.url };
          }
        }
        setPassportData(initialPassports);
      }
      if (statusRes) {
        setAnalysisStatus(statusRes.analysis_status);
        setAnalysisError(statusRes.analysis_error);
        if (statusRes.progress_step !== undefined) setProgressStep(statusRes.progress_step);
        if (statusRes.progress_percent !== undefined) setProgressPercent(statusRes.progress_percent);
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
          if (updated.progress_step !== undefined) setProgressStep(updated.progress_step);
          if (updated.progress_percent !== undefined) setProgressPercent(updated.progress_percent);
          if (updated.status === "ready") {
            const [mems, aliases, cms, statusRes, scoreRes] = await Promise.all([
              getProjectMembers(id),
              getProjectUnlinkedAliases(id),
              getProjectCommits(id, 50, 0),
              getAnalysisStatus(id),
              getProjectScores(id),
            ]);
            setMembers(Array.isArray(mems) ? mems : []);
            setUnlinkedAliases(Array.isArray(aliases) ? aliases : []);
            setCommits(Array.isArray(cms) ? cms : []);
            if (statusRes) {
              setAnalysisStatus(statusRes.analysis_status);
              setAnalysisError(statusRes.analysis_error);
              if (statusRes.progress_step !== undefined) setProgressStep(statusRes.progress_step);
              if (statusRes.progress_percent !== undefined) setProgressPercent(statusRes.progress_percent);
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
          if (statusRes.progress_step !== undefined) setProgressStep(statusRes.progress_step);
          if (statusRes.progress_percent !== undefined) setProgressPercent(statusRes.progress_percent);
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

  const handlePassportPublished = (memberId: string, code: string, url: string) => {
    setPassportData((prev) => ({
      ...prev,
      [memberId]: { code, url },
    }));
  };

  const handleRefreshDisputes = async () => {
    const updated = await listDisputes(id);
    setDisputes(Array.isArray(updated) ? updated : []);
  };

  const handleRefreshReviewers = async () => {
    const updated = await getProjectReviewers(id);
    setReviewersList(Array.isArray(updated) ? updated : []);
  };

  const handleRefreshSummaries = async () => {
    const updated = await getProjectSummaries(id);
    setSummaries(Array.isArray(updated) ? updated : []);
  };

  const handleRefreshOriginality = async () => {
    const updated = await getOriginalityMatches(id);
    setOriginalityResponse(updated);
  };

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

  // Collapsed header status text calculations
  const reviewersCount = reviewersList.length;
  const reviewersStatusText =
    reviewersCount === 0
      ? "No reviewers"
      : reviewersCount === 1
      ? "1 reviewer"
      : `${reviewersCount} reviewers`;

  const summariesStatusText =
    summaries.length > 0 ? "Generated" : "Not generated";

  const matchesCount = originalityResponse?.matches?.length ?? 0;
  const originalityStatusText = !originalityResponse
    ? "Not run"
    : matchesCount === 0
    ? "No similarities found"
    : matchesCount === 1
    ? "1 match"
    : `${matchesCount} matches`;

  return (
    <div className="min-h-full flex flex-col bg-bg">
      <header className="w-full h-[56px] border-b border-border bg-surface">
        <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
          <Link href="/dashboard" className="font-serif text-[18px] font-semibold text-text tracking-tight">
            Provenance
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-xs text-text-muted hover:text-text">
              &larr; Back to dashboard
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-8 space-y-8">
        {/* a. Header & b. Summary Line */}
        <ProjectHeader
          project={project}
          membersCount={members.length}
          isOwnerOrAdmin={isOwnerOrAdmin}
          canExport={canExport}
          actionLoading={actionLoading}
          confirmDelete={confirmDelete}
          onRecollect={handleRecollect}
          onDelete={handleDelete}
        />

        {/* Pending / Analyzing State */}
        {(project.status === "pending" || project.status === "analyzing") && (
          <div className="bg-surface border border-border rounded-[6px] p-8 text-center space-y-3">
            <p className="text-text font-medium text-[15px]">
              {progressStep || "Collecting repository history..."}
            </p>
            {typeof progressPercent === "number" && (
              <div className="max-w-[360px] mx-auto w-full bg-border rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-accent h-full transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(5, progressPercent))}%` }}
                />
              </div>
            )}
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
            {/* c. Contribution Scores */}
            <ScoresTable
              projectId={id}
              scores={scores}
              analysisStatus={analysisStatus}
              analysisError={analysisError}
              progressStep={progressStep}
              progressPercent={progressPercent}
              members={members}
              currentUser={currentUser}
              isOwnerOrAdmin={isOwnerOrAdmin}
              passportData={passportData}
              onAnalysisTriggered={() => {
                setAnalysisStatus("running");
                setProgressStep("Starting analysis...");
                setProgressPercent(70);
              }}
              onPassportPublished={handlePassportPublished}
              onDisputeSubmitted={handleRefreshDisputes}
            />

            {/* d. Members */}
            <MembersTable
              projectId={id}
              members={members}
              onDataChanged={loadData}
              readOnly={!isOwnerOrAdmin}
            />

            {/* e. Unlinked identities (only if any) */}
            {unlinkedAliases.length > 0 && (
              <UnlinkedIdentities
                projectId={id}
                unlinkedAliases={unlinkedAliases}
                members={members}
                onDataChanged={loadData}
                readOnly={!isOwnerOrAdmin}
              />
            )}

            {/* f. Recent Commits */}
            <RecentCommits commits={commits} />

            {/* Disputes Panel */}
            <DisputesPanel
              projectId={id}
              disputes={disputes}
              members={members}
              currentUser={currentUser}
              isOwnerOrAdmin={isOwnerOrAdmin}
              isAssignedFaculty={isAssignedFaculty}
              onDisputesChanged={handleRefreshDisputes}
            />

            {/* g. Three panels at the very bottom: Reviewers, Summaries, Originality */}
            <CollapsiblePanel
              id="reviewers"
              title="Project reviewers"
              description="Invited reviewers with review and dispute oversight access."
              statusText={reviewersStatusText}
            >
              <ReviewersPanel
                projectId={id}
                reviewers={reviewersList}
                isOwnerOrAdmin={isOwnerOrAdmin}
                onReviewersUpdated={handleRefreshReviewers}
                hideHeader={true}
              />
            </CollapsiblePanel>

            <CollapsiblePanel
              id="summaries"
              title="Evidence-grounded summaries"
              description="Natural language summaries of contributor achievements, audited against commit hashes."
              statusText={summariesStatusText}
            >
              <SummariesPanel
                projectId={id}
                repoFullName={project.repo_full_name}
                summaries={summaries}
                isOwnerOrAdmin={isOwnerOrAdmin}
                onSummariesUpdated={handleRefreshSummaries}
                analysisStatus={analysisStatus}
                hideHeader={true}
              />
            </CollapsiblePanel>

            <CollapsiblePanel
              id="originality"
              title="Originality and similarity check"
              description="Cross-repository fingerprint analysis to identify shared code blocks and templates."
              statusText={originalityStatusText}
            >
              <OriginalityPanel
                projectId={id}
                originalityResponse={originalityResponse}
                isOwnerOrAdmin={isOwnerOrAdmin}
                onCheckCompleted={handleRefreshOriginality}
                hideHeader={true}
              />
            </CollapsiblePanel>
          </>
        )}
      </main>
    </div>
  );
}
