"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import SignOutButton from "./SignOutButton";

interface TopBarProps {
  user: {
    username: string;
    avatar_url?: string | null;
    role?: "student" | "faculty" | "admin" | string | null;
  };
  pendingReviewsCount?: number;
}

export default function TopBar({ user, pendingReviewsCount: initialCount }: TopBarProps) {
  const pathname = usePathname();
  const [fetchedCount, setFetchedCount] = useState<number | null>(null);

  useEffect(() => {
    if (initialCount !== undefined) {
      return;
    }
    let isMounted = true;
    fetch("/api/reviews/summary")
      .then((res) => (res.ok ? res.json() : { pending_count: 0 }))
      .then((data) => {
        if (isMounted && typeof data.pending_count === "number") {
          setFetchedCount(data.pending_count);
        }
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, [initialCount]);

  const count = initialCount !== undefined ? initialCount : (fetchedCount ?? 0);

  const isReview = pathname.startsWith("/review");
  const isDashboard = !isReview && (pathname === "/dashboard" || pathname.startsWith("/projects"));

  return (
    <header className="w-full h-[56px] border-b border-border bg-surface">
      <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
        <div className="flex items-center gap-8 h-full">
          <Link
            href="/dashboard"
            className="font-serif text-[18px] font-semibold text-text tracking-tight select-none hover:text-accent transition-colors"
          >
            Provenance
          </Link>

          <nav className="flex items-center gap-6 h-full">
            <Link
              href="/dashboard"
              className={`h-full flex items-center text-[13px] font-medium transition-colors border-b-2 pt-[2px] ${
                isDashboard
                  ? "border-accent text-text"
                  : "border-transparent text-text-muted hover:text-text"
              }`}
            >
              My projects
            </Link>
            <Link
              href="/review"
              className={`h-full flex items-center gap-1.5 text-[13px] font-medium transition-colors border-b-2 pt-[2px] ${
                isReview
                  ? "border-accent text-text"
                  : "border-transparent text-text-muted hover:text-text"
              }`}
            >
              <span>Review</span>
              {count > 0 && (
                <span className="text-[12px] text-text-muted font-mono">{count}</span>
              )}
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          <nav className="flex items-center gap-3">
            {user.role === "admin" && (
              <Link
                href="/admin/users"
                className="text-text-muted hover:text-text text-[13px] font-medium transition-colors"
              >
                Admin
              </Link>
            )}
            <Link
              href="/account"
              className="text-text-muted hover:text-text text-[13px] font-medium transition-colors"
            >
              Account
            </Link>
            <Link
              href="/privacy"
              className="text-text-muted hover:text-text text-[13px] font-medium transition-colors"
            >
              Privacy
            </Link>
          </nav>

          <div className="h-4 w-[1px] bg-border" aria-hidden="true" />

          <div className="flex items-center gap-2">
            {user.avatar_url ? (
              <Image
                src={user.avatar_url}
                alt={`${user.username}'s avatar`}
                width={28}
                height={28}
                unoptimized
                className="w-7 h-7 rounded-[4px] border border-border shrink-0 object-cover"
              />
            ) : (
              <div
                className="w-7 h-7 rounded-[4px] bg-bg border border-border flex items-center justify-center text-xs font-mono font-medium text-text-muted"
                aria-label={`${user.username}'s avatar`}
              >
                {user.username.slice(0, 2).toUpperCase()}
              </div>
            )}
            <span className="text-text font-medium text-sm">
              {user.username}
            </span>
          </div>

          <div className="h-4 w-[1px] bg-border" aria-hidden="true" />

          <SignOutButton />
        </div>
      </div>
    </header>
  );
}
