import React from "react";

export default function EmptyState() {
  return (
    <div className="w-full bg-surface border border-border rounded-[6px] p-8 md:p-12 flex flex-col items-center justify-center text-center">
      <p className="text-text font-medium text-[15px] mb-4">
        No projects yet.
      </p>

      <div className="flex flex-col items-center gap-2">
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="btn-primary"
        >
          Add project
        </button>
        <span className="text-text-muted text-[12px]">
          Available in the next release.
        </span>
      </div>
    </div>
  );
}
