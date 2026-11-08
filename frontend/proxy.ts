import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Explicitly allow public access to passports, verification routes, and privacy page
  if (
    pathname.startsWith("/p/") ||
    pathname.startsWith("/verify/") ||
    pathname === "/privacy" ||
    pathname.startsWith("/privacy/")
  ) {
    return NextResponse.next();
  }

  const sessionCookie = request.cookies.get("provenance_session");

  if (!sessionCookie || !sessionCookie.value) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/account/:path*", "/admin/:path*"],
};

