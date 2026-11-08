import React from "react";
import Link from "next/link";

export default function PrivacyPage() {
  return (
    <div className="min-h-full flex flex-col bg-bg">
      <header className="w-full h-[56px] border-b border-border bg-surface">
        <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
          <Link
            href="/"
            className="font-serif text-[18px] font-semibold text-text tracking-tight hover:opacity-90"
          >
            Provenance
          </Link>

          <div className="flex items-center gap-4 text-xs">
            <Link
              href="/"
              className="text-text-muted hover:text-text font-medium transition-colors"
            >
              Home
            </Link>
            <Link
              href="/dashboard"
              className="text-text-muted hover:text-text font-medium transition-colors"
            >
              Dashboard
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-[800px] w-full mx-auto px-4 py-12 space-y-10">
        <div>
          <h1 className="font-serif text-[28px] sm:text-[34px] font-semibold text-text tracking-tight mb-2">
            Privacy Policy &amp; Data Transparency
          </h1>
          <p className="text-sm text-text-muted leading-relaxed">
            Provenance is committed to verifiable contribution attribution while maintaining absolute respect for student and developer privacy.
            This document outlines exactly what data is collected, how it is analyzed, and how you retain control over your information.
          </p>
        </div>

        {/* Section 1: What We Store */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-3">
          <h2 className="text-[16px] font-semibold text-text">
            1. What Data We Store
          </h2>
          <p className="text-xs text-text-muted leading-relaxed">
            When you sign in and collect repositories, Provenance stores the minimal metadata required to generate accurate contribution reports:
          </p>
          <ul className="list-disc list-inside text-xs text-text space-y-1.5 pl-2 leading-relaxed">
            <li><strong>Account profile:</strong> GitHub login username, display name, public avatar URL, public email (if shared on GitHub), and user ID.</li>
            <li><strong>Repository metadata:</strong> Repository name, URL, default branch, and collection timestamps.</li>
            <li><strong>Git commit metadata:</strong> Commit SHA hashes, commit timestamps, commit messages (subject lines), file counts, and net added/deleted line statistics.</li>
            <li><strong>Collaboration metrics:</strong> Pull request counts opened and code reviews submitted.</li>
            <li><strong>Contribution analysis:</strong> Computed contribution scores, signal breakdowns, originality fingerprint hashes (64-bit numerical hashes), and published passports.</li>
          </ul>
        </section>

        {/* Section 2: What We Do NOT Store */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-3">
          <h2 className="text-[16px] font-semibold text-text">
            2. What We Do NOT Store
          </h2>
          <p className="text-xs text-text-muted leading-relaxed">
            We follow a strict policy of data minimization:
          </p>
          <ul className="list-disc list-inside text-xs text-text space-y-1.5 pl-2 leading-relaxed">
            <li><strong>Full source code repositories:</strong> Repository code is cloned into isolated bare stores for statistical analysis and winnowing fingerprints only. Source code files are never persisted long-term or exposed publicly.</li>
            <li><strong>Execution of code:</strong> Repository code is never executed, built, or run in any runtime environment.</li>
            <li><strong>OAuth tokens:</strong> GitHub access tokens are kept only in secure, HTTP-only session cookies or encrypted using AES-256-GCM. We never store plaintext personal tokens.</li>
            <li><strong>Teammate personal emails:</strong> Unmatched commit emails are kept strictly within the repository scope and are never published outside the project.</li>
          </ul>
        </section>

        {/* Section 3: Data Visibility & Access Permissions */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-3">
          <h2 className="text-[16px] font-semibold text-text">
            3. Who Can See Your Data
          </h2>
          <p className="text-xs text-text-muted leading-relaxed">
            Data visibility is governed by strict role-based access controls:
          </p>
          <ul className="list-disc list-inside text-xs text-text space-y-1.5 pl-2 leading-relaxed">
            <li><strong>Project owner:</strong> Full access to manage the project, trigger analysis, invite or assign faculty, view originality reports, and generate summaries.</li>
            <li><strong>Assigned faculty:</strong> Granted read access to view contribution breakdowns, audit member scores, view originality similarities, and resolve student disputes.</li>
            <li><strong>Administrators:</strong> Granted oversight access to manage user account permissions and investigate platform errors.</li>
            <li><strong>Public passports:</strong> If you explicitly choose to publish a Contribution Passport, its evidence seal and QR code are publicly viewable by anyone who possesses the unique passport URL or verification code. Passports can be revoked by you at any time.</li>
          </ul>
        </section>

        {/* Section 4: AI & Large Language Model Usage */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-3">
          <h2 className="text-[16px] font-semibold text-text">
            4. AI &amp; Large Language Model Usage
          </h2>
          <p className="text-xs text-text-muted leading-relaxed">
            Provenance uses Anthropic&apos;s Claude models solely to produce readable natural language summaries of verified technical contributions.
            To protect your privacy and intellectual property:
          </p>
          <ul className="list-disc list-inside text-xs text-text space-y-1.5 pl-2 leading-relaxed">
            <li><strong>Zero source code transmitted:</strong> Prompts sent to the AI contain only aggregate factual metrics, commit hashes, and commit subject lines. No source code files are ever sent to language models.</li>
            <li><strong>Zero teammate identification:</strong> Prompts omit teammate names, emails, and identifiers to preserve peer anonymity.</li>
            <li><strong>Evidence grounding:</strong> AI summaries are strictly constrained to repository evidence and audited against committed commit SHAs. Any ungrounded claim triggers an immediate fallback to deterministic rule-based summaries.</li>
            <li><strong>No model training:</strong> All API requests are processed through zero-retention commercial enterprise endpoints that do not train on customer inputs.</li>
          </ul>
        </section>

        {/* Section 5: Your Rights & Account Deletion */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-3">
          <h2 className="text-[16px] font-semibold text-text">
            5. Your Rights &amp; Data Deletion
          </h2>
          <p className="text-xs text-text-muted leading-relaxed">
            You maintain absolute sovereignty over your records:
          </p>
          <ul className="list-disc list-inside text-xs text-text space-y-1.5 pl-2 leading-relaxed">
            <li><strong>Right to export:</strong> You can download a complete, machine-readable JSON snapshot of your data at any time from your Account Settings page.</li>
            <li><strong>Right to erasure (account deletion):</strong> You can permanently delete your Provenance account at any time. Deleting your account irrevocably purges all your owned projects, published passports, disputes, analysis records, and on-disk repository caches. Your original repositories on GitHub remain untouched.</li>
            <li><strong>Right to dispute:</strong> Students who believe their contributions have been misattributed or under-represented can raise a formal dispute for faculty review.</li>
          </ul>
        </section>

        {/* Section 6: Contact */}
        <section className="bg-surface border border-border rounded-[6px] p-6 space-y-2">
          <h2 className="text-[16px] font-semibold text-text">
            6. Institutional &amp; Privacy Inquiries
          </h2>
          <p className="text-xs text-text-muted leading-relaxed">
            If you have questions regarding academic integrity compliance, institutional deployments, or data handling policies,
            please contact the project administrator or email <span className="font-mono text-text">privacy@provenance.app</span>.
          </p>
        </section>
      </main>

      <footer className="w-full border-t border-border py-6 bg-surface/50">
        <div className="max-w-[1120px] mx-auto px-4 flex items-center justify-between text-xs text-text-muted">
          <span>Provenance &mdash; Evidence-backed contribution records</span>
          <span className="font-mono text-[11px]">Updated 2026</span>
        </div>
      </footer>
    </div>
  );
}

