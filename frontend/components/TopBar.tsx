import React from "react";
import Image from "next/image";
import SignOutButton from "./SignOutButton";

interface TopBarProps {
  user: {
    username: string;
    avatar_url?: string | null;
  };
}

export default function TopBar({ user }: TopBarProps) {
  return (
    <header className="w-full h-[56px] border-b border-border bg-surface">
      <div className="max-w-[1120px] h-full mx-auto px-4 flex items-center justify-between">
        <div className="flex items-center">
          <span className="font-serif text-[18px] font-semibold text-text tracking-tight select-none">
            Provenance
          </span>
        </div>

        <div className="flex items-center gap-3">
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

