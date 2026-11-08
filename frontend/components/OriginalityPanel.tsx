"use client";

import React, { useEffect, useState } from "react";
import { OriginalityResponse, getOriginalityAvailability, runOriginalityCheck } from "@/lib/api";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface OriginalityPanelProps {
  projectId: string;
  originalityResponse: OriginalityResponse | null;
  isOwnerOrAdmin: boolean;
  onCheckCompleted?: () => void;
  readOnly?: boolean;
  hideHeader?: boolean;
}

export default function OriginalityPanel({
  projectId,
  originalityResponse,
  isOwnerOrAdmin,
  onCheckCompleted,
  readOnly = false,
  hideHeader = false,
}: OriginalityPanelProps) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAvailable, setIsAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    let isMounted = true;
    getOriginalityAvailability(projectId)
      .then((res) => {
        if (isMounted) {
          setIsAvailable(res?.available ?? false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setIsAvailable(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [projectId]);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await runOriginalityCheck(projectId);
      if (res.ok) {
        onCheckCompleted?.();
      } else {
        setError(res.error || "Failed to run originality check.");
      }
    } catch {
      setError("Network error running originality check.");
    } finally {
      setRunning(false);
    }
  };

  const matches = Array.isArray(originalityResponse?.matches) ? originalityResponse.matches : [];
  const externalFlag = Boolean(originalityResponse?.external_similarity_flag);
  const externalCount = originalityResponse?.external_similarity_count ?? originalityResponse?.external_match_count ?? 1;
  const threshold = originalityResponse?.threshold_lines ?? 200;
  const standardNote = "Similarity can come from shared templates, tutorials or team collaboration. It is not a finding of misconduct.";

  return (
    <SectionErrorBoundary title="Originality & Similarity Check">
      <section className="space-y-3">
        {!hideHeader ? (
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider text-text-muted">
                Originality &amp; Similarity Check
              </h2>
              <p className="text-xs text-text-muted mt-0.5">
                Cross-repository winnowing fingerprint analysis to identify shared code blocks and templates.
              </p>
            </div>
            {isOwnerOrAdmin && !readOnly && (
              <button
                type="button"
                onClick={handleRun}
                disabled={running || isAvailable === false}
                title={
                  isAvailable === false
                    ? "Originality checks compare this project with other projects added to Provenance. No other projects are available yet."
                    : undefined
                }
                className="btn-secondary text-[12px] h-[30px] px-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {running ? "Scanning..." : "Run originality check"}
              </button>
            )}
          </div>
        ) : (
          isOwnerOrAdmin && !readOnly && (
            <div className="flex items-center justify-end pb-1">
              <button
                type="button"
                onClick={handleRun}
                disabled={running || isAvailable === false}
                title={
                  isAvailable === false
                    ? "Originality checks compare this project with other projects added to Provenance. No other projects are available yet."
                    : undefined
                }
                className="btn-secondary text-[12px] h-[30px] px-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {running ? "Scanning..." : "Run originality check"}
              </button>
            </div>
          )
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
          {isAvailable === false ? (
            <p className="text-xs text-text-muted">
              Originality checks compare this project with other projects added to Provenance. No other projects are available yet.
            </p>
          ) : !originalityResponse ? (
            <div className="text-center py-6 text-text-muted text-xs">
              No originality report available yet. Run a check to compare against other repositories.
            </div>
          ) : matches.length > 0 ? (
            <div className="space-y-4">
              <div className="p-3 bg-warning/10 border border-warning/30 rounded-[4px]">
                <h3 className="text-sm font-semibold text-warning">
                  Similarity found. Please review.
                </h3>
                <p className="text-xs text-text mt-1">
                  Shared fingerprint matches detected above threshold ({threshold} lines).
                </p>
                <p className="text-xs text-text-muted mt-1">
                  {standardNote}
                </p>
              </div>

              <div className="border border-border rounded-[4px] overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border bg-bg/50">
                      <th className="py-2 px-3 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Compared Repository
                      </th>
                      <th className="py-2 px-3 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                        Shared Lines (est.)
                      </th>
                      <th className="py-2 px-3 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                        Shared Fingerprints
                      </th>
                      <th className="py-2 px-3 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Matching Files
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border text-[13px]">
                    {matches.map((m, idx) => {
                      const topFiles = Array.isArray(m.top_files) ? m.top_files : [];
                      return (
                        <tr key={m.id || idx} className="hover:bg-bg/40 transition-colors">
                          <td className="py-2.5 px-3 font-mono text-text">
                            {m.other_project_name || m.other_repo_full_name || "Comparison repository"}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-text">
                            ~{m.shared_lines_estimate ?? 0}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-text-muted">
                            {m.shared_fingerprints ?? 0}
                          </td>
                          <td className="py-2.5 px-3">
                            {topFiles.length > 0 ? (
                              <div className="space-y-1">
                                {topFiles.map((tf, fIdx) => {
                                  const fileA = tf.path || tf.file || "unknown";
                                  const fileB = tf.other_path || tf.other_file || "";
                                  return (
                                    <div key={fIdx} className="font-mono text-xs text-text-muted">
                                      <span className="text-text">{fileA}</span>
                                      {fileB && fileB !== fileA && (
                                        <span> &harr; {fileB}</span>
                                      )}
                                      {typeof tf.count === "number" && (
                                        <span className="ml-1 text-[11px] text-text-muted">({tf.count} hashes)</span>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <span className="text-xs text-text-muted">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : externalFlag ? (
            <div className="space-y-3">
              <div className="p-3 bg-warning/10 border border-warning/30 rounded-[4px]">
                <h3 className="text-sm font-semibold text-warning">
                  Similarity found. Please review.
                </h3>
                <p className="text-xs text-text mt-1">
                  Similarity detected across {externalCount} external repository {externalCount === 1 ? "project" : "projects"}.
                </p>
                <p className="text-xs text-text-muted mt-1">
                  {standardNote}
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-[13px] text-text">
                No substantial similarity detected across comparison repositories (minimum threshold: {threshold} lines).
              </p>
              <p className="text-xs text-text-muted">
                {standardNote}
              </p>
            </div>
          )}
        </div>
      </section>
    </SectionErrorBoundary>
  );
}
