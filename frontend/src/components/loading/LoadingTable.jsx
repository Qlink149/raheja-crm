import React from "react";
import { CallRowSkeleton } from "../feedback/Skeletons";

/**
 * Table body skeleton — row placeholders during fetch.
 */
const LoadingTable = ({ rows = 5, columns = 7, RowSkeleton = CallRowSkeleton }) => (
  <div>
    {Array.from({ length: rows }).map((_, i) => (
      <RowSkeleton key={i} columns={columns} />
    ))}
  </div>
);

export default LoadingTable;
