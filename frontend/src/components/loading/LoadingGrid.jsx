import React from "react";
import { LeadGridSkeleton } from "../feedback/Skeletons";

/**
 * Card grid skeleton wrapper.
 */
const LoadingGrid = ({ count = 9, children, loading = false, hasData = true }) => {
  if (loading && !hasData) {
    return <LeadGridSkeleton count={count} />;
  }
  return children;
};

export default LoadingGrid;
