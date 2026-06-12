import React from "react";
import { ChartSkeleton } from "../feedback/Skeletons";

/**
 * Chart wrapper: shows skeleton during initial load, children when ready.
 */
const LoadingChart = ({ loading = false, hasData = true, tall = false, children, className = "" }) => {
  if (loading && !hasData) {
    return <ChartSkeleton tall={tall} />;
  }
  return <div className={className}>{children}</div>;
};

export default LoadingChart;
