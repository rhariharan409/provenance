import type { Metadata } from "next";
import PassportActions from "@/components/PassportActions";
import { getPublicPassportServer } from "@/lib/api";

export const metadata: Metadata = {
  title: "Contribution Passport - Provenance",
  robots: {
    index: false,
    follow: false,
  },
};

interface PassportPageProps {
  params: Promise<{ code: string }>;
}

export default async function PassportPage({ params }: PassportPageProps) {
  const { code } = await params;
  const passport = await getPublicPassportServer(code);

  if (!passport || passport.revoked) {
    return (
      <main className="min-h-screen flex items-center justify-center p-6 bg-bg text-text">
        <div className="max-w-[480px] w-full p-8 border border-border bg-surface rounded-[6px] text-center">
          <h1 className="font-serif text-2xl font-semibold mb-2">Provenance</h1>
          <p className="text-[14px] text-text-muted">This passport is not available.</p>
        </div>
      </main>
    );
  }

  const snapshot = passport?.snapshot;
  const project = snapshot?.project;
  const member = snapshot?.member;
  const score = snapshot?.score;
  const signals = snapshot?.signals;
  const evidence = snapshot?.evidence;
  const team = Array.isArray(snapshot?.team) ? snapshot.team : [];
  const notes = snapshot?.notes;
  const seal = passport?.seal || "";
  const seal_version = passport?.seal_version || "v1";
  const created_at = passport?.created_at;
  const dispute_summary = passport?.dispute_summary || { open: 0, resolved: 0, rejected: 0, total: 0 };

  // Format dispute line
  let disputeLine = "No disputes";
  if (dispute_summary.open > 0) {
    disputeLine = `${dispute_summary.open} dispute${dispute_summary.open > 1 ? "s" : ""} open`;
  } else if (dispute_summary.resolved > 0) {
    disputeLine = `${dispute_summary.resolved} dispute${dispute_summary.resolved > 1 ? "s" : ""} resolved`;
  } else if (dispute_summary.rejected > 0) {
    disputeLine = `${dispute_summary.rejected} dispute${dispute_summary.rejected > 1 ? "s" : ""} reviewed`;
  }

  // Format date
  const analysisDateStr = project.finished_at
    ? new Date(project.finished_at).toUTCString()
    : "Unknown date";
  const sealedDateStr = created_at
    ? new Date(created_at).toUTCString()
    : "Unknown date";

  return (
    <>
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: #FFFFFF !important; color: #000000 !important; }
          .passport-doc { max-width: 100% !important; border: none !important; padding: 0 !important; }
          .passport-section { break-inside: avoid; }
        }
      `}</style>

      <main className="min-h-screen py-10 px-4 sm:px-6 bg-bg text-text flex justify-center">
        <article className="passport-doc w-full max-w-[820px] bg-surface border border-border rounded-[6px] p-6 sm:p-10 flex flex-col gap-8">
          {/* Header */}
          <header className="passport-section border-b border-border pb-6 flex flex-col sm:flex-row justify-between sm:items-start gap-4">
            <div>
              <p className="text-[12px] uppercase tracking-wider text-text-muted font-medium mb-1">
                Evidence-backed record
              </p>
              <h1 className="font-serif text-3xl font-semibold text-text tracking-tight">
                Contribution Passport
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px]">
                <span className="font-semibold text-text">{member.display_name}</span>
                {member.login && (
                  <span className="font-mono text-text-muted text-[13px]">
                    @{member.login}
                  </span>
                )}
              </div>
            </div>

            <div className="text-left sm:text-right text-[13px] text-text-muted flex flex-col gap-1">
              <div>
                Repository:{" "}
                <a
                  href={project.github_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-accent hover:underline font-medium"
                >
                  {project.repo_full_name}
                </a>
              </div>
              <div>
                Analysis: <span className="font-mono">{analysisDateStr}</span>
              </div>
              <div>
                HEAD: <span className="font-mono">{typeof project?.head_sha === "string" && project.head_sha.length >= 7 ? project.head_sha.slice(0, 7) : (project?.head_sha || "—")}</span>
              </div>
            </div>
          </header>

          {/* Summary Section */}
          <section className="passport-section grid grid-cols-1 sm:grid-cols-3 gap-4 p-5 bg-bg border border-border rounded-[4px]">
            <div className="sm:col-span-1 border-b sm:border-b-0 sm:border-r border-border pb-4 sm:pb-0 sm:pr-4">
              <span className="text-[12px] text-text-muted uppercase tracking-wider block mb-1">
                Contribution Share
              </span>
              <span className="font-mono text-4xl font-semibold text-text tabular-nums">
                {Number(score?.share_percent || 0).toFixed(2)}%
              </span>
            </div>

            <div className="sm:col-span-2 flex flex-col justify-center gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[13px] text-text-muted">Confidence:</span>
                <span
                  className={`text-[12px] px-2 py-0.5 rounded-[4px] border font-medium uppercase tracking-wide ${
                    score?.confidence === "high"
                      ? "border-success text-success bg-[#2F6B3A]/10"
                      : score?.confidence === "medium"
                      ? "border-warning text-warning bg-[#8A5A00]/10"
                      : "border-border-strong text-text-muted bg-surface"
                    }`}
                >
                  {score?.confidence || "unknown"}
                </span>
              </div>

              {Array.isArray(score?.flags) && score.flags.length > 0 && (
                <div className="flex flex-col gap-1 mt-1">
                  {score.flags.map((f, i) => (
                    <div key={i} className="text-[12px] text-warning flex items-start gap-1">
                      <span className="font-mono font-medium">[{f.code}]</span>
                      <span>{f.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Signals Breakdown */}
          <section className="passport-section">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-text-muted mb-3">
              Signals
            </h2>
            <div className="border border-border rounded-[4px] overflow-hidden">
              <table className="w-full text-left text-[13px]">
                <thead className="bg-bg border-b border-border text-text-muted font-medium">
                  <tr>
                    <th className="py-2 px-3">Signal</th>
                    <th className="py-2 px-3 text-right">Raw Output</th>
                    <th className="py-2 px-3 text-right">Normalized</th>
                    <th className="py-2 px-3 text-right">Weight</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border font-mono text-[13px]">
                  {Object.entries(signals || {}).map(([key, val]) => (
                    <tr key={key}>
                      <td className="py-2 px-3 font-sans font-medium capitalize text-text">
                        {key.replace("_", " ")}
                      </td>
                      <td className="py-2 px-3 text-right text-text-muted">
                        {typeof val.raw === "number" ? val.raw.toFixed(1) : String(val.raw)}
                      </td>
                      <td className="py-2 px-3 text-right text-text">
                        {(val.normalized * 100).toFixed(1)}%
                      </td>
                      <td className="py-2 px-3 text-right text-text-muted">
                        {(val.weight * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Team Context */}
          {team && team.length > 0 && (
            <section className="passport-section">
              <h2 className="text-[13px] font-semibold uppercase tracking-wider text-text-muted mb-3">
                Team Context
              </h2>
              <div className="border border-border rounded-[4px] p-4 bg-surface">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {team.map((t, idx) => (
                    <div
                      key={idx}
                      className="p-3 border border-border bg-bg rounded-[4px] flex flex-col"
                    >
                      <span className="text-[13px] font-medium text-text truncate">
                        {t.label}
                      </span>
                      <span className="font-mono text-[16px] font-semibold text-text tabular-nums mt-1">
                        {t.share_percent.toFixed(2)}%
                      </span>
                      {t.has_passport && (
                        <span className="text-[11px] text-success font-medium mt-1">
                          Verified
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* Evidence Section */}
          <section className="passport-section flex flex-col gap-6">
            <div>
              <h2 className="text-[13px] font-semibold uppercase tracking-wider text-text-muted mb-3">
                Evidence
              </h2>

              {/* Top Commits */}
              {Array.isArray(evidence?.top_commits) && evidence.top_commits.length > 0 && (
                <div className="mb-4">
                  <h3 className="text-[13px] font-medium text-text mb-2">
                    Key Commits (effective change)
                  </h3>
                  <div className="border border-border rounded-[4px] overflow-hidden">
                    <table className="w-full text-left text-[13px]">
                      <thead className="bg-bg border-b border-border text-text-muted font-medium">
                        <tr>
                          <th className="py-2 px-3">Commit</th>
                          <th className="py-2 px-3">Subject</th>
                          <th className="py-2 px-3 text-right">Effective Lines</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {evidence.top_commits.map((c, i) => {
                          const shaShort = c.sha_short || (typeof c.sha === "string" && c.sha.length >= 7 ? c.sha.slice(0, 7) : "—");
                          return (
                            <tr key={i}>
                              <td className="py-2 px-3 font-mono text-[12px]">
                                {c.github_url ? (
                                  <a
                                    href={c.github_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-accent hover:underline"
                                  >
                                    {shaShort}
                                  </a>
                                ) : (
                                  shaShort
                                )}
                              </td>
                              <td className="py-2 px-3 text-text truncate max-w-[280px]">
                                {c.subject || "Untitled commit"}
                              </td>
                              <td className="py-2 px-3 text-right font-mono text-text-muted">
                                +{Number(c.effective_lines || 0).toFixed(1)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Top Files & Owned Modules */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {Array.isArray(evidence?.top_files) && evidence.top_files.length > 0 && (
                  <div>
                    <h3 className="text-[13px] font-medium text-text mb-2">
                      Surviving Files
                    </h3>
                    <div className="border border-border rounded-[4px] p-3 text-[13px] flex flex-col gap-1.5">
                      {evidence.top_files.map((f, i) => (
                        <div key={i} className="flex justify-between items-center gap-2">
                          <span className="font-mono text-[12px] truncate text-text">
                            {f.path}
                          </span>
                          <span className="font-mono text-[12px] text-text-muted shrink-0">
                            {f.surviving_lines} lines
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {Array.isArray(evidence?.owned_modules) && evidence.owned_modules.length > 0 && (
                  <div>
                    <h3 className="text-[13px] font-medium text-text mb-2">
                      Module Ownership
                    </h3>
                    <div className="border border-border rounded-[4px] p-3 text-[13px] flex flex-col gap-1.5">
                      {evidence.owned_modules.map((m, i) => (
                        <div key={i} className="flex justify-between items-center gap-2">
                          <span className="font-mono text-[12px] truncate text-text">
                            {m.module || m.path}
                          </span>
                          <span className="font-mono text-[12px] text-accent shrink-0">
                            {(Number(m.share || 0) * 100).toFixed(0)}% share
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Tamper-Evident Seal Block */}
          <section className="passport-section border border-border rounded-[6px] p-5 sm:p-6 bg-surface flex flex-col gap-5">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted block">
                  Cryptographic Seal (v{seal_version})
                </span>
                <p className="text-[13px] text-text font-medium mt-0.5">
                  Sealed by Provenance on {sealedDateStr}
                </p>
                <p className="text-[12px] text-text-muted mt-0.5">
                  Status: <span className="font-medium text-text">{disputeLine}</span>
                </p>
              </div>

              {/* QR Image */}
              <div className="shrink-0">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/public/passports/${code}/qr.svg`}
                  alt="Passport QR Code"
                  width={112}
                  height={112}
                  className="border border-border bg-white p-1 rounded-[4px]"
                />
              </div>
            </div>

            {/* Full HMAC Hash */}
            <div>
              <span className="text-[11px] text-text-muted block mb-1">
                HMAC-SHA256 Verification Hash:
              </span>
              <div className="p-3 bg-bg border border-border rounded-[4px] font-mono text-[12px] text-text break-all select-all">
                {seal}
              </div>
            </div>

            {/* Disclaimer & Integrity Note */}
            <div className="text-[12px] text-text-muted border-t border-border pt-3 flex flex-col gap-1 leading-relaxed">
              <p>{notes.disclaimer}</p>
              <p className="font-mono text-[11px]">
                Engine: v{notes.scoring_version} (Survival: {(notes.weights?.survival * 100 || 40).toFixed(0)}%, Change: {(notes.weights?.effective_change * 100 || 25).toFixed(0)}%, Ownership: {(notes.weights?.ownership * 100 || 15).toFixed(0)}%, Collaboration: {(notes.weights?.collaboration * 100 || 20).toFixed(0)}%)
              </p>
            </div>

            {/* Verification and Print Interactive Controls */}
            <PassportActions code={code} />
          </section>
        </article>
      </main>
    </>
  );
}
