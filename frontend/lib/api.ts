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
  owner_id?: string;
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
  user_id?: string | null;
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

export interface MemberScoreItem {
  member_id: string;
  display_name: string | null;
  github_login: string | null;
  share_percent: number;
  confidence: "high" | "medium" | "low";
  flags: string[];
  signals: Record<string, { raw: number; normalized: number; weight: number }>;
}

export interface ProjectScoresResponse {
  run_id: string;
  project_id: string;
  scoring_version: string;
  head_sha: string;
  finished_at: string | null;
  weights: Record<string, number>;
  stats: Record<string, unknown>;
  project_flags: Array<{ code: string; message: string }>;
  members: MemberScoreItem[];
}

export interface MemberEvidenceResponse {
  member_id: string;
  display_name: string | null;
  github_login: string | null;
  share_percent: number;
  confidence: string;
  top_commits: Array<{ sha: string; subject: string; effective_lines: number; commit_url: string }>;
  top_files: Array<{ path: string; surviving_lines: number }>;
  owned_modules: Array<{ path: string; share: number }>;
  summary_sentence: string;
  signals: Record<string, { raw: number; normalized: number; weight: number }>;
}

export interface AnalysisStatusResponse {
  analysis_status: string;
  analysis_error: string | null;
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

export async function getCurrentUserClient(): Promise<UserProfile | null> {
  try {
    const response = await fetch("/api/auth/me", {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    return await response.json();
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

/**
 * Fetches analysis status for a project.
 */
export async function getAnalysisStatus(
  projectId: string
): Promise<AnalysisStatusResponse | null> {
  try {
    const response = await fetch(`/api/projects/${projectId}/analysis/status`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Fetches latest complete scores for a project.
 */
export async function getProjectScores(
  projectId: string
): Promise<ProjectScoresResponse | null> {
  try {
    const response = await fetch(`/api/projects/${projectId}/scores`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Fetches evidence details for a specific member score.
 */
export async function getMemberEvidence(
  projectId: string,
  memberId: string
): Promise<MemberEvidenceResponse | null> {
  try {
    const response = await fetch(
      `/api/projects/${projectId}/scores/${memberId}/evidence`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      }
    );
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Triggers a re-analysis run for a project.
 */
export async function triggerAnalysis(projectId: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/projects/${projectId}/analyze`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Section 4: Passports & Disputes
// ---------------------------------------------------------------------------

export interface UserPassportItem {
  id: string;
  code: string;
  project_id: string;
  member_id?: string;
  project_name: string;
  share_percent: number;
  status: "active" | "revoked";
  created_at: string | null;
  view_count: number;
  dispute_summary: {
    open: number;
    resolved: number;
    rejected: number;
    total: number;
  };
  url: string;
}

export interface PublicPassportData {
  code: string;
  seal: string;
  seal_version: string;
  created_at: string | null;
  snapshot: {
    project: {
      repo_full_name: string;
      github_url: string;
      head_sha: string;
      finished_at: string | null;
    };
    member: {
      login: string;
      display_name: string;
    };
    score: {
      share_percent: number;
      confidence: string;
      flags: Array<{ code: string; message: string }>;
    };
    signals: Record<string, { raw: number; normalized: number; weight: number }>;
    stats: {
      counted_commits?: number;
      surviving_lines?: number;
    };
    evidence: {
      top_commits: Array<{
        sha: string;
        sha_short: string;
        subject: string;
        effective_lines: number;
        github_url: string;
      }>;
      top_files: Array<{ path: string; surviving_lines: number }>;
      owned_modules: Array<{ module?: string; path?: string; share: number; surviving_lines?: number }>;
    };
    team: Array<{
      label: string;
      login: string | null;
      share_percent: number;
      has_passport: boolean;
    }>;
    notes: {
      scoring_version: string;
      weights: Record<string, number>;
      disclaimer: string;
    };
  };
  dispute_summary: {
    open: number;
    resolved: number;
    rejected: number;
    total: number;
  };
  revoked: boolean;
}

export interface VerifyPassportResult {
  valid: boolean;
  seal_version: string;
  checked_at: string;
}

export interface DisputeItem {
  id: string;
  project_id: string;
  member_id: string;
  member_name: string;
  raised_by?: string;
  raised_by_username: string;
  text: string;
  status: "open" | "resolved" | "rejected";
  resolution_note: string | null;
  created_at: string | null;
  resolved_at: string | null;
}

export async function publishPassport(
  projectId: string,
  memberId: string
): Promise<{ ok: boolean; status: number; code?: string; url?: string; error?: string }> {
  try {
    const response = await fetch(`/api/projects/${projectId}/members/${memberId}/passport`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (response.ok) {
      const data = await response.json();
      return { ok: true, status: response.status, code: data.code, url: data.url };
    }
    const errData = await response.json().catch(() => ({}));
    return {
      ok: false,
      status: response.status,
      error: errData.detail || "Failed to publish passport.",
    };
  } catch {
    return { ok: false, status: 500, error: "Network error publishing passport." };
  }
}

export async function getMyPassportsServer(
  cookieHeader?: string
): Promise<UserPassportItem[]> {
  try {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (cookieHeader) {
      headers["Cookie"] = cookieHeader;
    }
    const response = await fetch(`${BACKEND_URL}/passports/mine`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

export async function getMyPassports(): Promise<UserPassportItem[]> {
  try {
    const response = await fetch("/api/passports/mine", {
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

export async function revokePassport(code: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/passports/${code}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function getPublicPassportServer(code: string): Promise<PublicPassportData | null> {
  try {
    const response = await fetch(`${BACKEND_URL}/public/passports/${code}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function verifyPassportClient(code: string): Promise<VerifyPassportResult | null> {
  try {
    const response = await fetch(`/api/public/passports/${code}/verify`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function createDispute(
  projectId: string,
  memberId: string,
  text: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`/api/projects/${projectId}/members/${memberId}/disputes`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ text }),
    });
    if (response.ok) return { ok: true };
    const errData = await response.json().catch(() => ({}));
    return { ok: false, error: errData.detail || "Failed to raise dispute." };
  } catch {
    return { ok: false, error: "Network error raising dispute." };
  }
}

export async function listDisputes(projectId: string): Promise<DisputeItem[]> {
  try {
    const response = await fetch(`/api/projects/${projectId}/disputes`, {
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

export async function resolveDispute(
  projectId: string,
  disputeId: string,
  status: "resolved" | "rejected",
  resolutionNote?: string
): Promise<{ ok: boolean; message?: string; error?: string }> {
  try {
    const response = await fetch(`/api/projects/${projectId}/disputes/${disputeId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ status, resolution_note: resolutionNote || null }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      return { ok: true, message: data.message };
    }
    return { ok: false, error: data.detail || "Failed to update dispute." };
  } catch {
    return { ok: false, error: "Network error updating dispute." };
  }
}

