import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import TopBar from "@/components/TopBar";
import ReviewClientPage from "./ReviewClientPage";
import {
  getCurrentUser,
  getMyReviewInvitations,
  getReviewedProjects,
  getReviewsSummary,
} from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("provenance_session");

  if (!sessionCookie?.value) {
    redirect("/");
  }

  const rawCookie = `provenance_session=${sessionCookie.value}`;
  const user = await getCurrentUser(rawCookie);

  if (!user) {
    redirect("/");
  }

  const [rawInvitations, rawProjects, reviewsSummary] = await Promise.all([
    getMyReviewInvitations(rawCookie),
    getReviewedProjects(rawCookie),
    getReviewsSummary(rawCookie),
  ]);

  const invitations = Array.isArray(rawInvitations) ? rawInvitations : [];
  const projects = Array.isArray(rawProjects) ? rawProjects : [];
  const pendingCount = reviewsSummary?.pending_count ?? 0;

  return (
    <div className="min-h-full flex flex-col bg-bg">
      <TopBar
        user={{
          username: user.username,
          avatar_url: user.avatar_url,
          role: user.role,
        }}
        pendingReviewsCount={pendingCount}
      />

      <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-8">
        <ReviewClientPage
          initialInvitations={invitations}
          initialProjects={projects}
        />
      </main>
    </div>
  );
}

