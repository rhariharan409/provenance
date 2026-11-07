import React from "react";
import Link from "next/link";

export default function EmptyState() {
  return (
    <div className="w-full bg-surface border border-border rounded-[6px] p-8 md:p-12 flex flex-col items-center justify-center text-center">
      <p className="text-text font-medium text-[15px] mb-4">
        No projects yet.
      </p>

      <div className="flex flex-col items-center gap-2">
        <Link href="/projects/new" className="btn-primary">
          Add project
        </Link>
      </div>
    </div>
  );
}
