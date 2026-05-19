import React from "react";

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#1A1A1A] border border-white/10 rounded-lg p-3 shadow-xl">
      <p className="text-[#C5A059] font-medium">{label || payload[0].payload?.name}</p>
      <p className="text-white">{payload[0].value} leads</p>
    </div>
  );
};

export default ChartTooltip;
