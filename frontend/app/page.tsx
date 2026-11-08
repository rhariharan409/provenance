import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import SignInButton from "@/components/SignInButton";
import { getCurrentUser } from "@/lib/api";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function LandingPage({ searchParams }: PageProps) {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("provenance_session");

  if (sessionCookie?.value) {
    const rawCookie = `provenance_session=${sessionCookie.value}`;
    const user = await getCurrentUser(rawCookie);
    if (user) {
      redirect("/dashboard");
    }
  }

  const resolvedParams = await searchParams;
  const isAuthFailed = resolvedParams.error === "auth_failed";

  return (
    <div className="min-h-full flex flex-col bg-bg">
      <header className="w-full h-[56px] border-b border-border bg-surface">
        <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center">
          <span className="font-serif text-[18px] font-semibold text-text tracking-tight select-none">
            Provenance
          </span>
        </div>
      </header>

      <main className="flex-1 flex flex-col justify-center max-w-[1120px] w-full mx-auto px-4 py-16 sm:py-24">
        <div className="max-w-[640px]">
          {isAuthFailed && (
            <div
              role="alert"
              className="mb-6 px-3 py-2 bg-surface border border-danger rounded-[4px] text-danger text-[13px] font-medium"
            >
              Sign-in failed. Please try again.
            </div>
          )}

          <h1 className="font-serif text-[32px] sm:text-[40px] font-semibold text-text leading-[1.2] tracking-tight mb-4">
            Evidence-backed records of who built what.
          </h1>

          <p className="text-[15px] sm:text-[16px] text-text-muted leading-[1.6] mb-8">
            Provenance analyzes a team&apos;s Git repository and produces a verifiable contribution report.
          </p>

          <div className="flex flex-col items-start gap-3">
            <SignInButton />
            <p className="text-[12px] text-text-muted">
              Read-only access. Your code is never executed.
            </p>
          </div>
        </div>
      </main>

      <footer className="w-full border-t border-border py-6 bg-surface/50">
        <div className="max-w-[1120px] mx-auto px-4 flex items-center justify-between text-xs text-text-muted">
          <span>Provenance &mdash; Evidence-backed contribution records</span>
          <a href="/privacy" className="hover:text-text transition-colors">
            Privacy Policy
          </a>
        </div>
      </footer>
    </div>
  );
}
