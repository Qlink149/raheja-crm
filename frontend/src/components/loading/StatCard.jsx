import React from "react";
import { KpiTileSkeleton } from "../feedback/Skeletons";

/**
 * KPI stat tile: skeleton while loading, value when ready, dash on error-without-data.
 */
const StatCard = ({
  label,
  value,
  icon: Icon,
  iconColor = "text-[#C5A059]",
  loading = false,
  hasData = true,
  error = false,
  className = "",
  onClick,
  formatValue = (v) => (typeof v === "number" ? v.toLocaleString() : v),
}) => {
  if (loading && !hasData) {
    return <KpiTileSkeleton />;
  }

  const displayValue =
    error && !hasData
      ? "—"
      : value == null
        ? "—"
        : formatValue(value);

  const interactive = Boolean(onClick);

  return (
    <div
      className={`glass-card rounded-lg p-4 border border-white/10 min-w-0 ${
        interactive ? "cursor-pointer hover:border-[#C5A059]/30 transition-colors" : ""
      } ${className}`}
      onClick={onClick}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.(e);
              }
            }
          : undefined
      }
    >
      {Icon && <Icon className={`w-5 h-5 ${iconColor} mb-2`} />}
      <p
        className="text-2xl font-semibold text-white tabular-nums truncate"
        title={String(displayValue)}
      >
        {displayValue}
      </p>
      <p className="text-xs text-[#737373] mt-1 truncate">{label}</p>
    </div>
  );
};

export default StatCard;
