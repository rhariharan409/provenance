"use client";

import React from "react";
import { ProjectDetail, getExportCsvUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface ProjectHeaderProps {
  project: ProjectDetail;
  membersCount: number;
  isOwnerOrAdmin: boolean;
  canExport: boolean;
  actionLoading: boolean;
  confirmDelete: boolean;
  onRecollect: () => void;
  onDelete: () => void;
}

export default function ProjectHeader({
  project,
  membersCount,
  isOwnerOrAdmin,
  canExport,
  actionLoading,
  confirmDelete,
  onRecollect,
  onDelete,
}: ProjectHeaderProps) {
  const lastCollectedStr = formatDateTime(project.last_collected_at);
  const commitsCount = project.commit_total || 0;
  const prsCount = project.prs_count ?? 0;

  const commitsLabel = commitsCount === 1 ? "1 commit" : `${commitsCount.toLocaleString()} commits`;
  const membersLabel = membersCount === 1 ? "1 member" : `${membersCount} members`;
  const prsLabel = prsCount === 1 ? "1 pull request" : `${prsCount} pull requests`;

  return (
    <SectionErrorBoundary title="Project Header">
      <div className="space-y-4">
        {/* Project Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-[20px] font-semibold text-text tracking-tight font-mono">
                {project.repo_full_name}
              </h1>
              <span
                className={`text-[11px] font-mono px-2 py-0.5 rounded-[3px] border uppercase ${
                  project.status === "ready"
                    ? "border-success text-success bg-success/5"
                    : project.status === "failed"
                    ? "border-danger text-danger bg-danger/5"
                    : "border-warning text-warning bg-warning/5"
                }`}
              >
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
            {canExport && (
              <a
                href={getExportCsvUrl(project.id)}
                className="btn-secondary text-[13px]"
                download={`provenance-${project.repo_full_name.replace("/", "-")}.csv`}
              >
                Export CSV
              </a>
            )}
            {isOwnerOrAdmin && (
              <>
                <button
                  type="button"
                  onClick={onRecollect}
                  disabled={actionLoading || project.status === "analyzing"}
                  className="btn-secondary text-[13px]"
                >
                  Re-run collection
                </button>
                <button
                  type="button"
                  onClick={onDelete}
                  disabled={actionLoading}
                  className={`btn-secondary text-[13px] ${confirmDelete ? "border-danger text-danger" : ""}`}
                >
                  {confirmDelete ? "Confirm delete" : "Delete project"}
                </button>
              </>
            )}
          </div>
        </div>

        {/* Warnings notice */}
        {project.warnings && (
          <div className="bg-surface border border-warning rounded-[4px] p-3 text-[13px] text-text">
            <span className="font-medium text-warning mr-1">Notice:</span>
            {project.warnings}
          </div>
        )}

        {/* Summary Line */}
        {project.status === "ready" && (
          <div className="bg-surface border border-border rounded-[6px] px-4 py-3 text-[13px] text-text font-mono flex flex-wrap gap-4 items-center">
            <span>
              <strong className="font-semibold text-text">{commitsLabel}</strong>
            </span>
            <span className="text-border-strong">•</span>
            <span>
              <strong className="font-semibold text-text">{membersLabel}</strong>
            </span>
            <span className="text-border-strong">•</span>
            <span>
              <strong className="font-semibold text-text">{prsLabel}</strong>
            </span>
            <span className="text-border-strong">•</span>
            <span className="text-text-muted">
              Last collected: <span className="tabular-nums text-text">{lastCollectedStr}</span>
            </span>
          </div>
        )}
      </div>
    </SectionErrorBoundary>
  );
}

