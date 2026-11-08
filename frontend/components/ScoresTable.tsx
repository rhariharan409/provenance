"use client";

import React from "react";
import ScoresPanel from "./ScoresPanel";
import {
  ProjectScoresResponse,
  MemberDetail,
  UserProfile,
} from "@/lib/api";

interface ScoresTableProps {
  projectId: string;
  scores: ProjectScoresResponse | null;
  analysisStatus: string;
  analysisError: string | null;
  progressStep?: string | null;
  progressPercent?: number | null;
  members: MemberDetail[];
  currentUser: UserProfile | null;
  isOwnerOrAdmin: boolean;
  passportData: Record<string, { code: string; url: string }>;
  onAnalysisTriggered?: () => void;
  onPassportPublished?: (memberId: string, code: string, url: string) => void;
  onDisputeSubmitted?: () => void;
  readOnly?: boolean;
}

export default function ScoresTable(props: ScoresTableProps) {
  return <ScoresPanel {...props} />;
}

