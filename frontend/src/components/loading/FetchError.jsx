import React from "react";
import { AlertCircle } from "lucide-react";
import { Button } from "../ui/button";

/**
 * Inline error card with retry — matches CampaignsPage pattern.
 */
const FetchError = ({
  title = "Failed to load data",
  message = "Something went wrong while fetching. Please try again.",
  onRetry,
  className = "",
}) => (
  <div
    className={`glass-card rounded-lg p-6 border border-red-500/20 bg-red-500/5 max-w-xl ${className}`}
    role="alert"
  >
    <div className="flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
      <div className="space-y-2 flex-1">
        <p className="text-white font-medium">{title}</p>
        <p className="text-[#A3A3A3] text-sm">{message}</p>
        {onRetry && (
          <Button
            variant="outline"
            className="mt-2 border-white/10 text-white hover:bg-white/5"
            onClick={onRetry}
          >
            Retry
          </Button>
        )}
      </div>
    </div>
  </div>
);

export default FetchError;
