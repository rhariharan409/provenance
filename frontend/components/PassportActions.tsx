"use client";

import { useState } from "react";
import { verifyPassportClient } from "@/lib/api";

interface PassportActionsProps {
  code: string;
}

export default function PassportActions({ code }: PassportActionsProps) {
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<"valid" | "invalid" | "error" | null>(null);

  const handleVerify = async () => {
    setVerifying(true);
    setResult(null);
    try {
      const res = await verifyPassportClient(code);
      if (res && res.valid) {
        setResult("valid");
      } else if (res && !res.valid) {
        setResult("invalid");
      } else {
        setResult("error");
      }
    } catch {
      setResult("error");
    } finally {
      setVerifying(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="no-print mt-6 flex flex-col gap-3 pt-4 border-t border-border">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={handleVerify}
          disabled={verifying}
          className="h-9 px-4 rounded-[4px] border border-accent bg-accent text-white text-[14px] font-medium transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {verifying ? "Verifying..." : "Verify seal"}
        </button>
        <button
          onClick={handlePrint}
          className="h-9 px-4 rounded-[4px] border border-border bg-surface text-text text-[14px] font-medium transition-colors hover:bg-bg"
        >
          Print or save as PDF
        </button>
      </div>

      {result === "valid" && (
        <div className="p-3 rounded-[4px] border border-success bg-[#2F6B3A]/10 text-success text-[13px] font-medium">
          Seal valid: record unchanged since it was issued
        </div>
      )}

      {result === "invalid" && (
        <div className="p-3 rounded-[4px] border border-danger bg-[#A32A2A]/10 text-danger text-[13px] font-medium">
          Seal does not match: this record may have been altered
        </div>
      )}

      {result === "error" && (
        <div className="p-3 rounded-[4px] border border-warning bg-[#8A5A00]/10 text-warning text-[13px] font-medium">
          Unable to verify seal at this moment. Please check connection.
        </div>
      )}
    </div>
  );
}
