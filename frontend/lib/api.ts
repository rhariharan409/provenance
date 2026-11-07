import { BACKEND_URL } from "./config";

export interface UserProfile {
  id: string;
  github_id: number;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  email: string | null;
  role: "student" | "faculty" | "admin";
  created_at: string;
  last_login_at: string | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  repo_full_name: string;
  repo_url: string;
  description: string | null;
  status: "pending" | "analyzing" | "ready" | "failed";
  is_private: boolean;
  commit_total: number;
  last_collected_at: string | null;
  created_at: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  default_branch: string | null;
  warnings: string | null;
  error_message: string | null;
  members_count: number;
  prs_count: number;
}

export interface MemberAlias {
  id: string;
  name: string;
  email: string;
  source: string;
  is_bot: boolean;
  commit_count: number;
}

export interface MemberDetail {
  id: string;
  login: string | null;
  display_name: string | null;
  commit_count: number;
  additions: number;
  deletions: number;
  pull_requests_opened: number;
  reviews_given: number;
  first_commit_at: string | null;
  last_commit_at: string | null;
  aliases: MemberAlias[];
}

export interface UnlinkedAlias {
  id: string;
  name: string;
  email: string;
  member_id: string | null;
  source: string;
  is_bot: boolean;
  commit_count: number;
}

export interface CommitItem {
  id: string;
  sha: string;
  author_name: string;
  author_email: string;
  authored_at: string | null;
  subject: string;
  additions: number;
  deletions: number;
  files_changed: number;
}

/**
 * Fetches the authenticated user profile from the backend.
 * When called on the server, forward the raw cookie string.
 */
export async function getCurrentUser(
  cookieHeader?: string
): Promise<UserProfile | null> {
  try {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (cookieHeader) {
      headers["Cookie"] = cookieHeader;
    }

    const response = await fetch(`${BACKEND_URL}/auth/me`, {
      method: "GET",
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    const data: UserProfile = await response.json();
    return data;
  } catch {
    return null;
  }
}

/**
 * Calls the logout endpoint to clear the session cookie.
 */
export async function logout(): Promise<boolean> {
  try {
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Fetches list of projects for current user.
 */
export async function getProjects(
  cookieHeader?: string
): Promise<ProjectSummary[]> {
  try {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (cookieHeader) {
      headers["Cookie"] = cookieHeader;
    }

    const url = cookieHeader ? `${BACKEND_URL}/projects` : "/api/projects";
    const response = await fetch(url, {
      method: "GET",
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      return [];
    }

    return await response.json();
  } catch {
    return [];
  }
}

/**
 * Fetches detail of a single project.
 */
export async function getProjectDetail(
  id: string,
  cookieHeader?: string
): Promise<ProjectDetail | null> {
  try {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (cookieHeader) {
      headers["Cookie"] = cookieHeader;
    }

    const url = cookieHeader
      ? `${BACKEND_URL}/projects/${id}`
      : `/api/projects/${id}`;

    const response = await fetch(url, {
      method: "GET",
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Submits a new project repository URL.
 */
export async function createProject(repo_url: string): Promise<{
  ok: boolean;
  status: number;
  data?: Record<string, unknown>;
  error?: string;
  code?: string;
  install_url?: string;
}> {
  try {
    const response = await fetch("/api/projects", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ repo_url }),
    });

    const body = await response.json();

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: body.detail || body.message || "Failed to create project.",
        code: body.code,
        install_url: body.install_url,
      };
    }

    return {
      ok: true,
      status: response.status,
      data: body,
    };
  } catch {
    return {
      ok: false,
      status: 500,
      error: "Network error. Please try again.",
    };
  }
}

/**
 * Triggers re-collection for a project.
 */
export async function recollectProject(id: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/projects/${id}/recollect`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Deletes a project.
 */
export async function deleteProject(id: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/projects/${id}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Fetches members of a project.
 */
export async function getProjectMembers(id: string): Promise<MemberDetail[]> {
  try {
    const response = await fetch(`/api/projects/${id}/members`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

/**
 * Fetches unlinked aliases of a project.
 */
export async function getProjectUnlinkedAliases(
  id: string
): Promise<UnlinkedAlias[]> {
  try {
    const response = await fetch(`/api/projects/${id}/aliases?linked=false`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

/**
 * Assigns an unlinked alias to a member.
 */
export async function assignAlias(
  projectId: string,
  aliasId: string,
  memberId: string
): Promise<boolean> {
  try {
    const response = await fetch(
      `/api/projects/${projectId}/aliases/${aliasId}/assign`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ member_id: memberId }),
      }
    );
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Merges source member into target member.
 */
export async function mergeMembers(
  projectId: string,
  sourceMemberId: string,
  targetMemberId: string
): Promise<boolean> {
  try {
    const response = await fetch(`/api/projects/${projectId}/members/merge`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        source_member_id: sourceMemberId,
        target_member_id: targetMemberId,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Fetches recent commits for a project.
 */
export async function getProjectCommits(
  projectId: string,
  limit: number = 50,
  offset: number = 0
): Promise<CommitItem[]> {
  try {
    const response = await fetch(
      `/api/projects/${projectId}/commits?limit=${limit}&offset=${offset}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      }
    );
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}
