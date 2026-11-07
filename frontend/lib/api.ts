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
