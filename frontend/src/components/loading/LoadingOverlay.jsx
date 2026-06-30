import React from "react";
import { Loader2 } from "lucide-react";

/**
 * Semi-transparent overlay shown during background refetches.
 * Keeps previous content visible underneath.
 */
const LoadingOverlay = ({ show, label = "Refreshing...", className = "" }) => {
  if (!show) return null;

  return (
    <div
      className={`absolute inset-0 z-10 flex items-center justify-center loading-overlay rounded-xl ${className}`}
      aria-live="polite"
      aria-busy="true"
    >
      <div className="loading-overlay-badge flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-[#C5A059]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>{label}</span>
      </div>
    </div>
  );
};

export default LoadingOverlay;
