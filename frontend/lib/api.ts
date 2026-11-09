import { BACKEND_URL } from "./config";
export { formatDate, formatDateTime } from "./date";

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
  history_window?: string | null;
  history_since?: string | null;
  history_window_months?: number | null;
  progress_step?: string | null;
  progress_percent?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
  clone_mode?: string | null;
  timings?: Record<string, number> | null;
  timing_stats?: Record<string, unknown> | null;
  estimated_commits?: number | null;
  partial_analysis?: boolean;
  analyzed_since?: string | null;
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
  history_window?: string | null;
  history_since?: string | null;
  timing_stats?: Record<string, unknown> | null;
  timings?: Record<string, number> | null;
  clone_mode?: string | null;
  partial_analysis?: boolean;
  analyzed_since?: string | null;
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
  progress_step?: string | null;
  progress_percent?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
  timings?: Record<string, number> | null;
  clone_mode?: string | null;
  partial_analysis?: boolean;
  analyzed_since?: string | null;
}

export interface RepoEstimate {
  repo_size_mb: number;
  default_branch: string;
  approximate_commits: number | null;
  is_private: boolean;
  recommendation: "full" | "window";
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
 * Estimates repository size and commit count before creating a project.
 */
export async function estimateProject(repo_url: string): Promise<RepoEstimate | null> {
  try {
    const params = new URLSearchParams({ repo_url });
    const response = await fetch(`/api/projects/estimate?${params.toString()}`, {
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
 * Submits a new project repository URL.
 */
export async function createProject(
  repo_url: string,
  history_window_months?: number | null,
  history_window?: string
): Promise<{
  ok: boolean;
  status: number;
  data?: Record<string, unknown>;
  error?: string;
  code?: string;
  install_url?: string;
}> {
  try {
    const payload: { repo_url: string; history_window?: string; history_window_months?: number | null } = { repo_url };
    if (history_window_months !== undefined && history_window_months !== null) {
      payload.history_window_months = history_window_months;
      payload.history_window = history_window_months > 0 ? `${history_window_months}m` : "all";
    } else if (history_window && history_window !== "all") {
      payload.history_window = history_window;
    }
    const response = await fetch("/api/projects", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
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
export async function recollectProject(
  id: string,
  history_window_months?: number | null
): Promise<boolean> {
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    let body: string | undefined = undefined;
    if (history_window_months !== undefined && history_window_months !== null) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify({ history_window_months });
    }
    const response = await fetch(`/api/projects/${id}/recollect`, {
      method: "POST",
      headers,
      body,
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
    if (!code) return false;
    const response = await fetch(`/api/passports/${encodeURIComponent(code)}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

export const revokePassportClient = revokePassport;

export async function getPublicPassportServer(code: string): Promise<PublicPassportData | null> {
  try {
    if (!code) return null;
    const response = await fetch(`${BACKEND_URL}/public/passports/${encodeURIComponent(code)}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (response.status === 404 || !response.ok) {
      return null;
    }
    return await response.json();
  } catch {
    return null;
  }
}

export const getPublicPassport = getPublicPassportServer;

export async function verifyPassportClient(code: string): Promise<VerifyPassportResult | null> {
  try {
    if (!code) return null;
    const response = await fetch(`/api/public/passports/${encodeURIComponent(code)}/verify`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export const verifyPassport = verifyPassportClient;

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

// ---------------------------------------------------------
// Section 5: Admin, Faculty, Summaries, Originality, Account
// ---------------------------------------------------------

export interface AdminUserItem {
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

export interface ProjectFacultyItem {
  id: string;
  user_id?: string;
  faculty_user_id?: string;
  username?: string;
  invitee_username?: string;
  display_name?: string | null;
  avatar_url?: string | null;
  status?: string;
  assigned_at?: string | null;
  created_at?: string | null;
  responded_at?: string | null;
  assigned_by?: string | null;
}

export interface FacultyProjectItem {
  id: string;
  name: string;
  repo_full_name: string;
  repo_url?: string;
  owner_id?: string;
  created_at?: string | null;
  assigned_at?: string | null;
  member_count?: number;
  members_count?: number;
  open_disputes_count: number;
  flags_count: number;
  status: string;
}

export interface CitationItem {
  sha?: string;
  sha_short?: string;
  claim?: string;
}

export interface MemberSummaryItem {
  id: string;
  run_id?: string;
  member_id: string;
  member?: string;
  member_name?: string;
  method?: "llm" | "rule_based" | string;
  text?: string;
  summary_text?: string;
  citations?: Array<string | CitationItem>;
  created_at?: string | null;
  generated_at?: string | null;
  disclaimer?: string;
}

export interface OriginalityMatchItem {
  id?: string;
  other_project_id?: string;
  other_project_name?: string;
  other_repo_full_name?: string;
  shared_fingerprints?: number;
  shared_lines_estimate?: number;
  top_files?: Array<{
    file?: string;
    other_file?: string;
    path?: string;
    other_path?: string;
    count?: number;
  }>;
  created_at?: string | null;
}

export interface OriginalityResponse {
  status?: string;
  heading?: string;
  matches: OriginalityMatchItem[];
  external_similarity_flag?: boolean;
  external_similarity_count?: number;
  external_match_count?: number;
  threshold_lines: number;
  disclaimer: string;
}

export async function getAdminUsers(
  query: string = "",
  limit: number = 50,
  offset: number = 0
): Promise<{ users: AdminUserItem[]; total: number }> {
  try {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (query) params.append("query", query);
    const response = await fetch(`/api/admin/users?${params.toString()}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return { users: [], total: 0 };
    const data = await response.json();
    if (Array.isArray(data)) {
      return { users: data, total: data.length };
    }
    return {
      users: Array.isArray(data?.users) ? data.users : [],
      total: typeof data?.total === "number" ? data.total : (data?.users?.length || 0),
    };
  } catch {
    return { users: [], total: 0 };
  }
}

export async function updateUserRole(
  userId: string,
  role: "student" | "faculty" | "admin"
): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`/api/admin/users/${encodeURIComponent(userId)}/role`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ role }),
    });
    if (response.ok) return { ok: true };
    const errData = await response.json().catch(() => ({}));
    return { ok: false, error: errData.detail || "Failed to update role." };
  } catch {
    return { ok: false, error: "Network error updating role." };
  }
}

export async function getProjectFaculty(projectId: string): Promise<ProjectFacultyItem[]> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/faculty`, {
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

export async function assignProjectFaculty(
  projectId: string,
  username: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/faculty`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username }),
    });
    if (response.ok) return { ok: true };
    const errData = await response.json().catch(() => ({}));
    return { ok: false, error: errData.detail || "Failed to assign faculty." };
  } catch {
    return { ok: false, error: "Network error assigning faculty." };
  }
}

export async function removeProjectFaculty(
  projectId: string,
  userId: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/faculty/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    if (response.ok) return { ok: true };
    const errData = await response.json().catch(() => ({}));
    return { ok: false, error: errData.detail || "Failed to remove faculty." };
  } catch {
    return { ok: false, error: "Network error removing faculty." };
  }
}

export async function getFacultyAssignedProjects(): Promise<FacultyProjectItem[]> {
  try {
    const response = await fetch(`/api/faculty/projects`, {
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

export async function getFacultyAssignedProjectsServer(rawCookie?: string): Promise<FacultyProjectItem[]> {
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (rawCookie) headers["Cookie"] = rawCookie;
    const response = await fetch(`${BACKEND_URL}/faculty/projects`, {
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

export function getExportCsvUrl(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/export.csv`;
}

export interface ProjectSummariesResult extends Array<MemberSummaryItem> {
  ok?: boolean;
  status?: number;
  needs_analysis?: boolean;
  error?: string;
  summaries?: MemberSummaryItem[];
}

export async function generateProjectSummaries(
  projectId: string
): Promise<{ ok: boolean; count?: number; message?: string; error?: string; status?: number; needs_analysis?: boolean }> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/summaries/generate`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      return { ok: true, count: Array.isArray(data) ? data.length : data.count, message: data.message };
    }
    const statusMsg = response.status ? ` (status ${response.status})` : "";
    const detailMsg = data.detail || "";
    const isNeedsAnalysis = detailMsg.toLowerCase().includes("analysis") || response.status === 400;
    return {
      ok: false,
      status: response.status,
      needs_analysis: isNeedsAnalysis,
      error: detailMsg ? `${detailMsg}${response.status >= 500 ? statusMsg : ""}` : `Could not generate summaries (status ${response.status})`,
    };
  } catch {
    return { ok: false, status: 500, error: "Could not generate summaries (status 500)" };
  }
}

export async function getProjectSummaries(projectId: string): Promise<ProjectSummariesResult> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/summaries`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      const errList = [] as ProjectSummariesResult;
      errList.ok = false;
      errList.status = response.status;
      errList.error = `Could not load summaries (status ${response.status})`;
      return errList;
    }
    const data = await response.json().catch(() => ({}));
    const needsAnalysis = Boolean(
      (data && typeof data === "object" && !Array.isArray(data) && data.needs_analysis) ||
      response.headers.get("x-needs-analysis") === "true"
    );
    const rawItems: MemberSummaryItem[] = Array.isArray(data)
      ? data
      : (data && Array.isArray(data.summaries) ? data.summaries : []);

    const resultList = [...rawItems] as ProjectSummariesResult;
    resultList.ok = true;
    resultList.status = response.status;
    resultList.needs_analysis = needsAnalysis;
    return resultList;
  } catch {
    const errList = [] as ProjectSummariesResult;
    errList.ok = false;
    errList.status = 500;
    errList.error = "Could not load summaries (status 500)";
    return errList;
  }
}

export async function runOriginalityCheck(
  projectId: string
): Promise<{ ok: boolean; message?: string; matches_count?: number; error?: string }> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/originality/run`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      return { ok: true, message: data.message, matches_count: data.matches_count };
    }
    return { ok: false, error: data.detail || "Failed to run originality check." };
  } catch {
    return { ok: false, error: "Network error running originality check." };
  }
}

export async function getOriginalityAvailability(
  projectId: string
): Promise<{ available: boolean }> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/originality/availability`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return { available: false };
    return await response.json();
  } catch {
    return { available: false };
  }
}

export async function getOriginalityMatches(projectId: string): Promise<OriginalityResponse | null> {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/originality`, {
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

export async function exportMyData(): Promise<Record<string, unknown> | null> {
  try {
    const response = await fetch(`/api/me/export`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function deleteMyAccount(confirmText: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`/api/me`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ confirm: confirmText }),
    });
    if (response.ok) return { ok: true };
    const data = await response.json().catch(() => ({}));
    return { ok: false, error: data.detail || "Failed to delete account." };
  } catch {
    return { ok: false, error: "Network error deleting account." };
  }
}

export interface ReviewSummaryResponse {
  pending_count: number;
}

export interface ReviewInvitationItem {
  id: string;
  project_id: string;
  project_name: string;
  repo_name: string;
  repo_full_name: string;
  invited_by: string;
  created_at: string | null;
  status: "pending" | "accepted" | "declined";
}

export interface ReviewedProjectItem {
  id: string;
  name: string;
  repo_name: string;
  repo_full_name: string;
  status: string;
  member_count: number;
  open_disputes_count: number;
  flags_count: number;
  accepted_at: string | null;
  created_at: string | null;
}

export interface ProjectReviewerItem {
  id: string;
  invitee_username: string;
  status: "pending" | "accepted" | "declined";
  created_at: string | null;
  responded_at?: string | null;
  type?: string;
  role?: string;
  assigned_by?: string | null;
}

export async function getReviewsSummary(cookieHeader?: string): Promise<ReviewSummaryResponse> {
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (cookieHeader) headers["Cookie"] = cookieHeader;
    const url = cookieHeader ? `${BACKEND_URL}/reviews/summary` : "/api/reviews/summary";
    const res = await fetch(url, { headers, cache: "no-store" });
    if (!res.ok) return { pending_count: 0 };
    return await res.json();
  } catch {
    return { pending_count: 0 };
  }
}

export async function getMyReviewInvitations(cookieHeader?: string): Promise<ReviewInvitationItem[]> {
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (cookieHeader) headers["Cookie"] = cookieHeader;
    const url = cookieHeader ? `${BACKEND_URL}/reviews/invitations` : "/api/reviews/invitations";
    const res = await fetch(url, { headers, cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function acceptReviewInvitation(invitationId: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(`/api/reviews/invitations/${encodeURIComponent(invitationId)}/accept`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (res.ok) return { ok: true };
    const err = await res.json().catch(() => ({}));
    return { ok: false, error: err.detail || "Failed to accept invitation." };
  } catch {
    return { ok: false, error: "Network error accepting invitation." };
  }
}

export async function declineReviewInvitation(invitationId: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(`/api/reviews/invitations/${encodeURIComponent(invitationId)}/decline`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (res.ok) return { ok: true };
    const err = await res.json().catch(() => ({}));
    return { ok: false, error: err.detail || "Failed to decline invitation." };
  } catch {
    return { ok: false, error: "Network error declining invitation." };
  }
}

export async function getReviewedProjects(cookieHeader?: string): Promise<ReviewedProjectItem[]> {
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (cookieHeader) headers["Cookie"] = cookieHeader;
    const url = cookieHeader ? `${BACKEND_URL}/reviews/projects` : "/api/reviews/projects";
    const res = await fetch(url, { headers, cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function leaveReviewedProject(projectId: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(`/api/reviews/projects/${encodeURIComponent(projectId)}/leave`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (res.ok) return { ok: true };
    const err = await res.json().catch(() => ({}));
    return { ok: false, error: err.detail || "Failed to leave review." };
  } catch {
    return { ok: false, error: "Network error leaving review." };
  }
}

export async function inviteProjectReviewer(
  projectId: string,
  username: string
): Promise<{ ok: boolean; error?: string; reviewer?: ProjectReviewerItem }> {
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/reviewers`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      return { ok: true, reviewer: data.reviewer };
    }
    return { ok: false, error: data.detail || "Failed to invite reviewer." };
  } catch {
    return { ok: false, error: "Network error inviting reviewer." };
  }
}

export async function getProjectReviewers(
  projectId: string,
  cookieHeader?: string
): Promise<ProjectReviewerItem[]> {
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (cookieHeader) headers["Cookie"] = cookieHeader;
    const url = cookieHeader
      ? `${BACKEND_URL}/projects/${encodeURIComponent(projectId)}/reviewers`
      : `/api/projects/${encodeURIComponent(projectId)}/reviewers`;
    const res = await fetch(url, { headers, cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function removeProjectReviewer(
  projectId: string,
  reviewerId: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(
      `/api/projects/${encodeURIComponent(projectId)}/reviewers/${encodeURIComponent(reviewerId)}`,
      {
        method: "DELETE",
        headers: { Accept: "application/json" },
      }
    );
    if (res.ok) return { ok: true };
    const err = await res.json().catch(() => ({}));
    return { ok: false, error: err.detail || "Failed to remove reviewer." };
  } catch {
    return { ok: false, error: "Network error removing reviewer." };
  }
}

