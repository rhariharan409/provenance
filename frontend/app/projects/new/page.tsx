"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createProject, estimateProject, RepoEstimate } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState("");
  const [historyMonths, setHistoryMonths] = useState<number>(0);
  const [estimate, setEstimate] = useState<RepoEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installUrl, setInstallUrl] = useState<string | null>(null);

  // Debounced estimation when URL looks valid
  useEffect(() => {
    const trimmed = repoUrl.trim();
    const timer = setTimeout(async () => {
      if (!trimmed.startsWith("https://github.com/") || trimmed.split("/").length < 5) {
        setEstimate(null);
        return;
      }
      setEstimating(true);
      const est = await estimateProject(trimmed);
      setEstimating(false);
      if (est) {
        setEstimate(est);
        if (est.recommendation === "window") {
          setHistoryMonths(12);
        } else {
          setHistoryMonths(0);
        }
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [repoUrl]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim() || loading) return;

    setLoading(true);
    setError(null);
    setInstallUrl(null);

    try {
      const res = await createProject(repoUrl.trim(), historyMonths);
      if (res.ok && res.data && typeof res.data.id === "string") {
        router.push(`/projects/${res.data.id}`);
      } else {
        setError(res.error || "Failed to add project.");
        if (res.code === "app_not_installed" && res.install_url) {
          setInstallUrl(res.install_url);
        }
      }
    } catch {
      setError("An unexpected error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-full flex flex-col bg-bg">
      <header className="w-full h-[56px] border-b border-border bg-surface">
        <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
          <Link
            href="/dashboard"
            className="font-serif text-[18px] font-semibold text-text tracking-tight hover:opacity-90"
          >
            Provenance
          </Link>
          <Link
            href="/dashboard"
            className="text-sm text-text-muted hover:text-text transition-colors duration-120"
          >
            Back to dashboard
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-12 flex justify-center items-start">
        <div className="w-full max-w-[560px] bg-surface border border-border rounded-[6px] p-6">
          <h1 className="text-[18px] font-semibold text-text tracking-tight mb-2">
            Add project
          </h1>
          <p className="text-[13px] text-text-muted mb-6">
            Provenance will clone the repository history and analyze evidence-backed contributions.
          </p>

          {error && (
            <div
              role="alert"
              className="mb-6 p-3 bg-surface border border-danger rounded-[4px] text-danger text-[13px]"
            >
              <p className="mb-2 font-medium">{error}</p>
              {installUrl && (
                <div className="mt-3">
                  <a
                    href={installUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary text-[13px] inline-flex"
                  >
                    Install GitHub App
                  </a>
                </div>
              )}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="repo_url"
                className="block text-[12px] font-medium uppercase tracking-wider text-text-muted mb-1.5"
              >
                Repository URL
              </label>
              <input
                id="repo_url"
                type="text"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                required
                className="w-full h-[36px] px-3 font-mono text-[13px] bg-surface border border-border rounded-[4px] text-text placeholder:text-text-muted/60 focus:outline-none focus:border-border-strong"
              />
              <p className="mt-2 text-[12px] text-text-muted">
                Public repositories work immediately. For private repositories, install the Provenance GitHub App on the repository first.
              </p>
            </div>

            {estimating && (
              <div className="p-3 bg-bg border border-border rounded-[4px] text-[12px] text-text-muted font-mono animate-pulse">
                Estimating repository size and commits...
              </div>
            )}

            {estimate && !estimating && (
              <div className="p-3 bg-bg border border-border rounded-[4px] text-[13px] space-y-1 font-mono">
                <div className="flex justify-between">
                  <span className="text-text-muted">Repository size:</span>
                  <span className="text-text font-medium">{estimate.repo_size_mb} MB</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Approximate commits:</span>
                  <span className="text-text font-medium">
                    {estimate.approximate_commits !== null
                      ? estimate.approximate_commits.toLocaleString()
                      : "Unknown"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Default branch:</span>
                  <span className="text-text font-medium">{estimate.default_branch}</span>
                </div>
                <div className="flex justify-between pt-1 border-t border-border">
                  <span className="text-text-muted">Recommendation:</span>
                  <span className="text-accent font-medium">
                    {estimate.recommendation === "window"
                      ? "Window recommended (Large repo)"
                      : "Full history"}
                  </span>
                </div>
              </div>
            )}

            <div>
              <label
                htmlFor="history_window"
                className="block text-[12px] font-medium uppercase tracking-wider text-text-muted mb-1.5"
              >
                History to analyze
              </label>
              <select
                id="history_window"
                value={historyMonths}
                onChange={(e) => setHistoryMonths(Number(e.target.value))}
                className="w-full h-[36px] px-3 font-mono text-[13px] bg-surface border border-border rounded-[4px] text-text focus:outline-none focus:border-border-strong"
              >
                <option value={0}>All history</option>
                <option value={24}>Last 24 months</option>
                <option value={12}>Last 12 months</option>
                <option value={6}>Last 6 months</option>
                <option value={3}>Last 3 months</option>
              </select>
              <p className="mt-2 text-[12px] text-text-muted">
                Large repositories are analyzed over a shorter window to stay fast. You can re-run with a different window later.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-between">
              <button
                type="submit"
                disabled={loading || !repoUrl.trim()}
                className="btn-primary"
              >
                {loading ? "Adding project..." : "Add project"}
              </button>
              <Link
                href="/dashboard"
                className="text-sm text-text-muted hover:text-text"
              >
                Cancel
              </Link>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
