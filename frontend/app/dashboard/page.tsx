import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import TopBar from "@/components/TopBar";
import EmptyState from "@/components/EmptyState";
import { getCurrentUser, getProjects } from "@/lib/api";

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

  const projects = await getProjects(rawCookie);

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
            <Link href="/projects/new" className="btn-primary">
              Add project
            </Link>
          </div>

          {projects.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="bg-surface border border-border rounded-[6px] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border bg-bg/50">
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Name
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Status
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider text-right">
                        Commits
                      </th>
                      <th className="py-2.5 px-4 font-medium text-text-muted text-[12px] uppercase tracking-wider">
                        Last Collected
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {projects.map((p) => {
                      const lastCollectedStr = p.last_collected_at
                        ? new Date(p.last_collected_at)
                            .toISOString()
                            .replace("T", " ")
                            .replace(/\..+/, " UTC")
                        : "—";

                      return (
                        <tr
                          key={p.id}
                          className="hover:bg-bg/40 transition-colors duration-120"
                        >
                          <td className="py-3 px-4">
                            <Link
                              href={`/projects/${p.id}`}
                              className="font-mono text-[13px] text-accent hover:underline font-medium"
                            >
                              {p.repo_full_name}
                            </Link>
                            {p.is_private && (
                              <span className="ml-2 text-[11px] font-mono border border-border px-1.5 py-0.5 rounded-[3px] text-text-muted">
                                private
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <span className="inline-block text-[12px] font-medium border border-border px-2 py-0.5 rounded-[4px] bg-surface capitalize text-text">
                              {p.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-[13px] tabular-nums text-text">
                            {p.commit_total.toLocaleString()}
                          </td>
                          <td className="py-3 px-4 font-mono text-[13px] tabular-nums text-text-muted">
                            {lastCollectedStr}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
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
