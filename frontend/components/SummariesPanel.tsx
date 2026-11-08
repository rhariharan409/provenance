"use client";

import React, { useState } from "react";
import {
  MemberSummaryItem,
  ProjectSummariesResult,
  generateProjectSummaries,
  getProjectSummaries,
} from "@/lib/api";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface SummariesPanelProps {
  projectId: string;
  repoFullName?: string;
  summaries: MemberSummaryItem[];
  isOwnerOrAdmin: boolean;
  onSummariesUpdated?: () => void;
  readOnly?: boolean;
  analysisStatus?: string;
  hideHeader?: boolean;
}

export default function SummariesPanel({
  projectId,
  repoFullName,
  summaries,
  isOwnerOrAdmin,
  onSummariesUpdated,
  readOnly = false,
  analysisStatus,
  hideHeader = false,
}: SummariesPanelProps) {
  const [generatedSummaries, setGeneratedSummaries] = useState<MemberSummaryItem[] | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const isAnalysisComplete = analysisStatus === "complete";
  const currentSummaries = generatedSummaries ?? summaries;
  const safeSummaries = Array.isArray(currentSummaries) ? currentSummaries : [];

  const handleGenerate = async () => {
    if (!isAnalysisComplete) {
      setError("Run analysis first.");
      return;
    }

    setGenerating(true);
    setError(null);
    setNotice(null);

    try {
      const res = await generateProjectSummaries(projectId);
      if (!res.ok) {
        if (res.needs_analysis || res.error?.toLowerCase().includes("analysis") || res.status === 400) {
          setError("Run analysis first.");
        } else {
          setError(res.error || `Could not load summaries (status ${res.status || 500})`);
        }
        return;
      }

      // Refetch GET /projects/{id}/summaries and render results
      const updated = await getProjectSummaries(projectId);
      if (updated.needs_analysis) {
        setError("Run analysis first.");
        return;
      }

      if (updated.ok === false) {
        setError(updated.error || `Could not load summaries (status ${updated.status || 500})`);
        return;
      }

      if (!Array.isArray(updated) || updated.length === 0) {
        setError("Could not load summaries (status 500)");
        return;
      }

      setGeneratedSummaries(updated);
      setNotice(res.message || "Summaries successfully generated.");
      onSummariesUpdated?.();
    } catch {
      setError("Could not load summaries (status 500)");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <SectionErrorBoundary title="Evidence-Grounded Summaries">
      <section className="space-y-3">
        {!hideHeader ? (
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
                Evidence-Grounded Summaries
              </h2>
              <p className="text-xs text-text-muted mt-0.5">
                Natural language summaries of contributor achievements, audited against commit hashes.
              </p>
            </div>
            {isOwnerOrAdmin && !readOnly && (
              <div className="flex items-center gap-2">
                {!isAnalysisComplete && (
                  <span className="text-xs text-text-muted">Run analysis first.</span>
                )}
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={generating || !isAnalysisComplete}
                  title={!isAnalysisComplete ? "Run analysis first." : undefined}
                  className="btn-secondary text-[12px] h-[30px] px-3 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {generating ? "Generating..." : "Generate summaries"}
                </button>
              </div>
            )}
          </div>
        ) : (
          isOwnerOrAdmin && !readOnly && (
            <div className="flex items-center justify-end gap-2 pb-1">
              {!isAnalysisComplete && (
                <span className="text-xs text-text-muted">Run analysis first.</span>
              )}
              <button
                type="button"
                onClick={handleGenerate}
                disabled={generating || !isAnalysisComplete}
                title={!isAnalysisComplete ? "Run analysis first." : undefined}
                className="btn-secondary text-[12px] h-[30px] px-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {generating ? "Generating..." : "Generate summaries"}
              </button>
            </div>
          )
        )}

        {notice && (
          <div className="p-2.5 bg-success/10 border border-success/30 rounded-[4px] text-xs text-success flex items-center justify-between">
            <span>{notice}</span>
            <button onClick={() => setNotice(null)} className="text-xs text-success/70 hover:text-success">
              Dismiss
            </button>
          </div>
        )}

        {error && (
          <div className="p-2.5 bg-danger/10 border border-danger/30 rounded-[4px] text-xs text-danger flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-xs text-danger/70 hover:text-danger">
              Dismiss
            </button>
          </div>
        )}

        <div className={hideHeader ? "" : "bg-surface border border-border rounded-[6px] p-4"}>
          {safeSummaries.length === 0 ? (
            <div className="text-center py-6 text-text-muted text-xs">
              {!isAnalysisComplete || Boolean((currentSummaries as ProjectSummariesResult)?.needs_analysis)
                ? "Run analysis first."
                : "No evidence-grounded summaries generated yet. Click \"Generate summaries\" to build audited descriptions."}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {safeSummaries.map((s) => {
                const textContent = s.text || s.summary_text || "No summary text available.";
                const rawCitations = Array.isArray(s.citations) ? s.citations : [];
                const memberDisplayName = s.member || s.member_name || "Contributor";
                const methodLabel =
                  s.method === "llm"
                    ? "Generated by AI from repository evidence"
                    : "Generated from repository evidence";

                return (
                  <div key={s.id} className="py-3.5 first:pt-0 last:pb-0 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-[13px] text-text">
                        {memberDisplayName}
                      </span>
                      <span className="font-mono text-[11px] text-text-muted px-1.5 py-0.5 bg-bg border border-border rounded-[3px]">
                        {methodLabel}
                      </span>
                    </div>

                    <p className="text-[13px] text-text leading-relaxed font-sans whitespace-pre-wrap">
                      {textContent}
                    </p>

                    {rawCitations.length > 0 && (
                      <div className="pt-2 flex flex-wrap items-center gap-1.5 text-xs">
                        <span className="text-text-muted font-medium text-[11px] uppercase tracking-wider mr-1">
                          Citations:
                        </span>
                        {rawCitations.map((c, cIdx) => {
                          let sha = "";
                          let claim = "";

                          if (typeof c === "string") {
                            sha = c.replace(/^\[+|\]+$/g, "").trim();
                          } else if (c && typeof c === "object") {
                            const obj = c as { sha?: unknown; sha_short?: unknown; claim?: unknown };
                            if (typeof obj.sha === "string") {
                              sha = obj.sha.trim();
                            } else if (typeof obj.sha_short === "string") {
                              sha = obj.sha_short.trim();
                            }
                            if (typeof obj.claim === "string") {
                              claim = obj.claim;
                            }
                          }

                          const isShaValid = typeof sha === "string" && sha.length >= 7;
                          if (!isShaValid) {
                            return null;
                          }

                          const shortSha = sha.slice(0, 7);
                          const commitUrl = repoFullName
                            ? `https://github.com/${repoFullName}/commit/${sha}`
                            : undefined;

                          return (
                            <a
                              key={`${sha}-${cIdx}`}
                              href={commitUrl || "#"}
                              target={commitUrl ? "_blank" : undefined}
                              rel="noopener noreferrer"
                              className="font-mono text-accent hover:underline text-[12px] bg-bg px-1.5 py-0.5 rounded border border-border transition-colors"
                              title={claim ? `${claim} (${sha})` : `View commit ${sha}`}
                            >
                              {shortSha}
                            </a>
                          );
                        })}
                      </div>
                    )}

                    {s.disclaimer && (
                      <p className="text-[11px] text-text-muted pt-1 border-t border-border/50">
                        {s.disclaimer}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </SectionErrorBoundary>
  );
}
