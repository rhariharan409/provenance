"use client";

import React, { useCallback, useSyncExternalStore } from "react";
import { SectionErrorBoundary } from "./SectionErrorBoundary";

interface CollapsiblePanelProps {
  id: string;
  title: string;
  description: string;
  statusText: string;
  children: React.ReactNode;
}

export default function CollapsiblePanel({
  id,
  title,
  description,
  statusText,
  children,
}: CollapsiblePanelProps) {
  const subscribe = useCallback(
    (callback: () => void) => {
      const handler = (e: StorageEvent) => {
        if (!e.key || e.key === `provenance_panel_${id}`) {
          callback();
        }
      };
      window.addEventListener("storage", handler);
      return () => window.removeEventListener("storage", handler);
    },
    [id]
  );

  const getSnapshot = useCallback(() => {
    try {
      return localStorage.getItem(`provenance_panel_${id}`) === "true";
    } catch {
      return false;
    }
  }, [id]);

  const getServerSnapshot = () => false;

  const isOpen = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const handleToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    const nextState = e.currentTarget.open;
    try {
      localStorage.setItem(`provenance_panel_${id}`, String(nextState));
      window.dispatchEvent(
        new StorageEvent("storage", { key: `provenance_panel_${id}` })
      );
    } catch {
      // Ignore localStorage errors
    }
  };

  return (
    <SectionErrorBoundary title={title}>
      <details
        className="bg-surface border border-border rounded-[4px] overflow-hidden"
        open={isOpen}
        onToggle={handleToggle}
      >
        <summary className="cursor-pointer p-4 select-none list-none [&::-webkit-details-marker]:hidden flex items-center justify-between gap-4 hover:bg-bg/40 transition-colors">
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] font-semibold text-text uppercase tracking-wider">
              {title}
            </h2>
            <p className="text-xs text-text-muted mt-0.5 truncate">{description}</p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="font-mono text-[12px] text-text-muted">{statusText}</span>
            <span className="text-xs text-accent font-medium">{isOpen ? "Hide" : "Show"}</span>
          </div>
        </summary>
        <div className="border-t border-border p-4">{children}</div>
      </details>
    </SectionErrorBoundary>
  );
}
