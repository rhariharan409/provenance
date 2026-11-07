"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { logout } from "@/lib/api";

export default function SignOutButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const handleSignOut = async () => {
    if (loading) return;
    setLoading(true);
    try {
      await logout();
    } finally {
      router.push("/");
      router.refresh();
    }
  };

  return (
    <button
      type="button"
      onClick={handleSignOut}
      disabled={loading}
      className="btn-secondary"
    >
      {loading ? "Signing out..." : "Sign out"}
    </button>
  );
}
