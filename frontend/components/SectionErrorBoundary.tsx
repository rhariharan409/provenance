"use client";

import React, { Component, ReactNode, ErrorInfo } from "react";

interface Props {
  children: ReactNode;
  title?: string;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class SectionErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("SectionErrorBoundary caught an error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="bg-surface border border-border rounded-[6px] p-6 text-center my-4 space-y-2">
          {this.props.title && (
            <h3 className="text-[13px] font-semibold text-text uppercase tracking-wider text-text-muted">
              {this.props.title}
            </h3>
          )}
          <p className="text-xs text-text-muted">
            {this.props.fallbackMessage || "This section could not be loaded."}
          </p>
        </div>
      );
    }

    return this.props.children;
  }
}

