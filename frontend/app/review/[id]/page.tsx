"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import TopBar from "@/components/TopBar";
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
  getProjectScores,
  getAnalysisStatus,
  getCurrentUserClient,
  listDisputes,
  getProjectReviewers,
  getProjectSummaries,
  getOriginalityMatches,
  getExportCsvUrl,
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

export default function ReviewProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [members, setMembers] = useState<MemberDetail[]>([]);
  const [unlinkedAliases, setUnlinkedAliases] = useState<UnlinkedAlias[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [scores, setScores] = useState<ProjectScoresResponse | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<string>("pending");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [progressStep, setProgressStep] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState<number | null>(null);
  const [progressCurrent, setProgressCurrent] = useState<number | null>(null);
  const [progressTotal, setProgressTotal] = useState<number | null>(null);
  const [disputes, setDisputes] = useState<DisputeItem[]>([]);
  const [reviewersList, setReviewersList] = useState<ProjectReviewerItem[]>([]);
  const [summaries, setSummaries] = useState<MemberSummaryItem[]>([]);
  const [originalityResponse, setOriginalityResponse] = useState<OriginalityResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const loadDisputes = useCallback(async () => {
    if (!id) return;
    const dispList = await listDisputes(id);
    setDisputes(Array.isArray(dispList) ? dispList : []);
  }, [id]);

  const loadData = useCallback(async () => {
    if (!id) return;

    const [userProfile, proj] = await Promise.all([
      getCurrentUserClient(),
      getProjectDetail(id),
    ]);

    if (userProfile) {
      setCurrentUser(userProfile);
    } else {
      router.push("/");
      return;
    }

    if (!proj) {
      setNotFound(true);
      setLoading(false);
      return;
    }

    setProject(proj);
    if (proj.progress_step !== undefined) setProgressStep(proj.progress_step);
    if (proj.progress_percent !== undefined) setProgressPercent(proj.progress_percent);
    if (proj.progress_current !== undefined) setProgressCurrent(proj.progress_current);
    if (proj.progress_total !== undefined) setProgressTotal(proj.progress_total);

    if (proj.status === "ready") {
      const [mems, aliases, cms, statusRes, scoreRes, dispList, revList, sums, orig] = await Promise.all([
        getProjectMembers(id),
        getProjectUnlinkedAliases(id),
        getProjectCommits(id, 50, 0),
        getAnalysisStatus(id),
        getProjectScores(id),
        listDisputes(id),
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

      if (statusRes) {
        setAnalysisStatus(statusRes.analysis_status);
        setAnalysisError(statusRes.analysis_error);
        if (statusRes.progress_step !== undefined) setProgressStep(statusRes.progress_step);
        if (statusRes.progress_percent !== undefined) setProgressPercent(statusRes.progress_percent);
        if (statusRes.progress_current !== undefined) setProgressCurrent(statusRes.progress_current);
        if (statusRes.progress_total !== undefined) setProgressTotal(statusRes.progress_total);
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
          if (updated.progress_current !== undefined) setProgressCurrent(updated.progress_current);
          if (updated.progress_total !== undefined) setProgressTotal(updated.progress_total);
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
              if (statusRes.progress_current !== undefined) setProgressCurrent(statusRes.progress_current);
              if (statusRes.progress_total !== undefined) setProgressTotal(statusRes.progress_total);
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
          if (statusRes.progress_current !== undefined) setProgressCurrent(statusRes.progress_current);
          if (statusRes.progress_total !== undefined) setProgressTotal(statusRes.progress_total);
          if (statusRes.analysis_status === "complete") {
            const scoreRes = await getProjectScores(id);
            if (scoreRes) {
              setScores(scoreRes);
            }
          }
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [id, project, analysisStatus]);

  if (loading) {
    return (
      <div className="min-h-full flex flex-col bg-bg">
        {currentUser && (
          <TopBar
            user={{
              username: currentUser.username,
              avatar_url: currentUser.avatar_url,
              role: currentUser.role,
            }}
          />
        )}
        <div className="flex-1 flex items-center justify-center p-8">
          <span className="text-sm text-text-muted">Loading project review...</span>
        </div>
      </div>
    );
  }

  if (notFound || !project) {
    return (
      <div className="min-h-full flex flex-col bg-bg">
        {currentUser && (
          <TopBar
            user={{
              username: currentUser.username,
              avatar_url: currentUser.avatar_url,
              role: currentUser.role,
            }}
          />
        )}
        <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-16 text-center space-y-4">
          <h1 className="text-xl font-semibold text-text">
            This project is not available.
          </h1>
          <p className="text-sm text-text-muted">
            The project you are looking for does not exist or you do not have permission to review it.
          </p>
          <div className="pt-2">
            <Link href="/review" className="btn-secondary text-xs">
              &larr; Back to Review
            </Link>
          </div>
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
      {currentUser && (
        <TopBar
          user={{
            username: currentUser.username,
            avatar_url: currentUser.avatar_url,
            role: currentUser.role,
          }}
        />
      )}

      <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-8 space-y-8">
        {/* Navigation & Read-Only Banner */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Link
              href="/review"
              className="text-accent hover:underline text-[13px] font-medium inline-flex items-center gap-1.5"
            >
              &larr; Back to Review
            </Link>
            <a
              href={getExportCsvUrl(id)}
              className="btn-secondary text-xs h-[30px] px-3 inline-flex items-center"
              download
            >
              Export CSV
            </a>
          </div>

          <div className="p-3 bg-surface border border-border rounded-[4px] text-[13px] text-text-muted flex items-center justify-between">
            <span>You are reviewing this project (read-only).</span>
          </div>
        </div>

        {/* a. Header & b. Summary Line */}
        <ProjectHeader
          project={project}
          membersCount={members.length}
          isOwnerOrAdmin={false}
          canExport={false}
          actionLoading={false}
          confirmDelete={false}
          onRecollect={() => {}}
          onDelete={() => {}}
        />

        {/* Pending / Analyzing State */}
        {(project.status === "pending" || project.status === "analyzing") && (
          <div className="bg-surface border border-border rounded-[6px] p-8 text-center space-y-3">
            <p className="text-text font-medium text-[15px]">
              {progressStep || "Collecting repository history..."}{" "}
              {typeof progressTotal === "number" && progressTotal > 0
                ? `(${progressCurrent?.toLocaleString() ?? 0} / ${progressTotal.toLocaleString()})`
                : ""}
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
            <p className="text-text-muted text-[13px]">
              Cloning repository history and mapping author identities. This page will update automatically.
            </p>
          </div>
        )}

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
          isOwnerOrAdmin={false}
          passportData={{}}
          readOnly={true}
        />

        {/* d. Members */}
        <MembersTable
          projectId={id}
          members={members}
          readOnly={true}
        />

        {/* e. Unlinked identities (only if any) */}
        {unlinkedAliases.length > 0 && (
          <UnlinkedIdentities
            projectId={id}
            unlinkedAliases={unlinkedAliases}
            members={members}
            readOnly={true}
          />
        )}

        {/* f. Recent Commits */}
        <RecentCommits commits={commits} />

        {/* Disputes */}
        <DisputesPanel
          projectId={id}
          disputes={disputes}
          members={members}
          currentUser={currentUser}
          isOwnerOrAdmin={false}
          isAssignedFaculty={true}
          onDisputesChanged={loadDisputes}
        />

        {/* g. Three collapsible panels at the very bottom: Reviewers, Summaries, Originality */}
        <CollapsiblePanel
          id="reviewers"
          title="Project reviewers"
          description="Invited reviewers with review and dispute oversight access."
          statusText={reviewersStatusText}
        >
          <ReviewersPanel
            projectId={id}
            reviewers={reviewersList}
            isOwnerOrAdmin={false}
            onReviewersUpdated={() => {}}
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
            isOwnerOrAdmin={false}
            readOnly={true}
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
            isOwnerOrAdmin={false}
            readOnly={true}
            hideHeader={true}
          />
        </CollapsiblePanel>
      </main>
    </div>
  );
}
