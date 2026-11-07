import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import TopBar from "@/components/TopBar";
import EmptyState from "@/components/EmptyState";
import { getCurrentUser } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
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

  const formattedLastLogin = user.last_login_at
    ? new Date(user.last_login_at).toISOString().replace("T", " ").replace(/\..+/, " UTC")
    : "—";

  return (
    <div className="min-h-full flex flex-col bg-bg">
      <TopBar
        user={{
          username: user.username,
          avatar_url: user.avatar_url,
        }}
      />

      <main className="flex-1 max-w-[1120px] w-full mx-auto px-4 py-8 space-y-8">
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h1 className="text-[20px] font-semibold text-text tracking-tight">
              Projects
            </h1>
          </div>
          <EmptyState />
        </section>

        <section className="space-y-3">
          <h2 className="text-[13px] font-semibold text-text uppercase tracking-wider text-text-muted">
            Account
          </h2>

          <div className="bg-surface border border-border rounded-[6px] p-5">
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4 text-sm">
              <div className="flex flex-col">
                <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                  Username
                </dt>
                <dd className="text-text font-mono text-[13px] break-all">
                  {user.username}
                </dd>
              </div>

              <div className="flex flex-col">
                <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                  Display name
                </dt>
                <dd className="text-text break-words">
                  {user.display_name || "—"}
                </dd>
              </div>

              <div className="flex flex-col">
                <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                  Email
                </dt>
                <dd className="text-text font-mono text-[13px] break-all">
                  {user.email || "—"}
                </dd>
              </div>

              <div className="flex flex-col">
                <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                  Role
                </dt>
                <dd className="text-text capitalize">
                  {user.role}
                </dd>
              </div>

              <div className="flex flex-col sm:col-span-2">
                <dt className="text-text-muted text-[12px] font-medium uppercase tracking-wider mb-1">
                  Last sign-in
                </dt>
                <dd className="text-text font-mono text-[13px] tabular-nums">
                  {formattedLastLogin}
                </dd>
              </div>
            </dl>
          </div>
        </section>
      </main>
    </div>
  );
}
