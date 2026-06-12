import React from "react";
import { KpiTileSkeleton } from "../feedback/Skeletons";
import StatCard from "./StatCard";

/**
 * Grid of StatCards with optional skeleton placeholders during initial load.
 */
const StatGrid = ({
  items = [],
  loading = false,
  hasData = true,
  error = false,
  columns = "grid-cols-2 md:grid-cols-4",
  className = "",
}) => {
  if (loading && !hasData) {
    return (
      <div className={`grid ${columns} gap-4 ${className}`}>
        {items.map((_, i) => (
          <KpiTileSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className={`grid ${columns} gap-4 ${className}`}>
      {items.map((item) => (
        <StatCard
          key={item.label}
          {...item}
          loading={loading}
          hasData={hasData}
          error={error}
        />
      ))}
    </div>
  );
};

export default StatGrid;
