import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Explicitly allow public access to passports and verification routes
  if (pathname.startsWith("/p/") || pathname.startsWith("/verify/")) {
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
  matcher: ["/dashboard/:path*"],
};

