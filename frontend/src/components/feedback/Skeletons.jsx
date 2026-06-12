/**
 * Premium skeleton screens.
 *
 * All variants use the `.skeleton-block` (with built-in shimmer sweep) defined
 * in index.css. Layouts mirror the actual page structure so the user perceives
 * the destination immediately while data loads.
 */

const Bar = ({ className = "" }) => (
  <div className={`skeleton-block ${className}`} />
);

/* ---------- KPI tile (Dashboard) ---------- */
export const KpiTileSkeleton = () => (
  <div className="glass-card rounded-lg p-6">
    <div className="flex items-start justify-between mb-4">
      <Bar className="w-11 h-11 rounded-lg" />
      <Bar className="w-12 h-5 rounded-md" />
    </div>
    <Bar className="w-24 h-3 mb-3 rounded" />
    <Bar className="w-32 h-9 rounded" />
  </div>
);

/* ---------- Alert tile (Cold / Dormant) ---------- */
export const AlertTileSkeleton = () => (
  <div className="glass-card rounded-lg p-5 border-l-4 border-l-white/5">
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-4">
        <Bar className="w-12 h-12 rounded-lg" />
        <div className="space-y-2">
          <Bar className="w-28 h-3 rounded" />
          <Bar className="w-20 h-8 rounded" />
        </div>
      </div>
      <div className="space-y-2 text-right">
        <Bar className="w-24 h-3 rounded ml-auto" />
        <Bar className="w-28 h-3 rounded ml-auto" />
      </div>
    </div>
  </div>
);

/* ---------- Chart block ---------- */
export const ChartSkeleton = ({ tall = false }) => (
  <div className="glass-card rounded-lg p-6">
    <Bar className="w-40 h-3 mb-6 rounded" />
    <div className={`flex items-end justify-between gap-3 ${tall ? "h-72" : "h-56"}`}>
      {[60, 80, 45, 90, 55, 75, 35, 65].map((h, i) => (
        <Bar key={i} className="flex-1 rounded-md" style={{ height: `${h}%` }} />
      ))}
    </div>
  </div>
);

/* ---------- Full dashboard layout ---------- */
export const DashboardSkeleton = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <AlertTileSkeleton />
      <AlertTileSkeleton />
    </div>
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {[0, 1, 2, 3].map((i) => (
        <KpiTileSkeleton key={i} />
      ))}
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-8">
        <ChartSkeleton tall />
      </div>
      <div className="lg:col-span-4">
        <ChartSkeleton />
      </div>
    </div>
  </div>
);

/* ---------- Lead card (VirtualCustomer grid) ---------- */
export const LeadCardSkeleton = () => (
  <div className="glass-card rounded-lg p-5">
    <div className="flex items-start gap-4">
      <Bar className="w-14 h-14 rounded-full flex-shrink-0" />
      <div className="flex-1 space-y-2 min-w-0">
        <Bar className="w-32 h-4 rounded" />
        <Bar className="w-40 h-3 rounded" />
        <div className="flex gap-2 mt-2">
          <Bar className="w-14 h-5 rounded" />
          <Bar className="w-20 h-5 rounded" />
        </div>
      </div>
    </div>
    <div className="mt-4 pt-3 border-t border-white/5 flex justify-between">
      <Bar className="w-16 h-4 rounded" />
      <Bar className="w-20 h-3 rounded" />
    </div>
  </div>
);

export const LeadGridSkeleton = ({ count = 9 }) => (
  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
    {Array.from({ length: count }).map((_, i) => (
      <LeadCardSkeleton key={i} />
    ))}
  </div>
);

/* ---------- Call row (AI Calling table) ---------- */
export const CALL_TABLE_GRID_COLS =
  "grid gap-2 [grid-template-columns:minmax(0,1.3fr)_minmax(0,1fr)_minmax(11.5rem,1.5fr)_minmax(3.5rem,0.5fr)_minmax(0,1fr)_minmax(0,0.9fr)_auto]";

export const CallRowSkeleton = () => (
  <div className={`${CALL_TABLE_GRID_COLS} px-4 py-4 items-center border-b border-white/5`}>
    <div className="flex items-center gap-3 min-w-0">
      <Bar className="w-8 h-8 rounded-full flex-shrink-0" />
      <Bar className="w-24 h-3 rounded" />
    </div>
    <Bar className="w-28 h-3 rounded" />
    <Bar className="w-32 h-3 rounded" />
    <Bar className="w-14 h-3 rounded" />
    <Bar className="w-20 h-5 rounded" />
    <Bar className="w-20 h-5 rounded" />
    <Bar className="w-20 h-7 rounded" />
  </div>
);

export const CallStatsSkeleton = () => (
  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
    {[0, 1, 2, 3, 4].map((i) => (
      <div key={i} className="glass-card rounded-xl p-6">
        <div className="flex items-center gap-3 mb-3">
          <Bar className="w-10 h-10 rounded-lg" />
          <Bar className="w-20 h-3 rounded" />
        </div>
        <Bar className="w-16 h-8 rounded" />
      </div>
    ))}
  </div>
);

export const CallTableSkeleton = ({ rows = 8 }) => (
  <div className="space-y-6">
    <CallStatsSkeleton />
    <div className="glass-card rounded-xl p-5">
      <Bar className="w-48 h-4 mb-4 rounded" />
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Bar key={i} className="h-14 rounded-lg" />
        ))}
      </div>
    </div>
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="p-4 border-b border-white/10">
        <Bar className="w-32 h-4 rounded mb-2" />
        <Bar className="w-48 h-3 rounded" />
      </div>
      <div className={`${CALL_TABLE_GRID_COLS} px-4 py-3 bg-[#1A1A1A] border-b border-white/10`}>
        {Array.from({ length: 7 }).map((_, i) => (
          <Bar key={i} className="h-3 rounded" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <CallRowSkeleton key={i} />
      ))}
    </div>
  </div>
);

/* ---------- Campaign page layout ---------- */
export const CampaignHeaderSkeleton = () => (
  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
    <div className="space-y-3">
      <Bar className="w-64 h-7 rounded" />
      <Bar className="w-80 h-3 rounded" />
    </div>
    <Bar className="w-36 h-10 rounded-lg" />
  </div>
);

export const CampaignSkeleton = () => (
  <div className="space-y-6">
    <CampaignHeaderSkeleton />
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
      <div className="glass-card rounded-lg p-6 space-y-4">
        <Bar className="w-48 h-4 rounded" />
        <div className="grid grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-2">
              <Bar className="w-24 h-3 rounded" />
              <Bar className="w-32 h-4 rounded" />
            </div>
          ))}
        </div>
      </div>
      <div className="glass-card rounded-lg p-6 space-y-3">
        <Bar className="w-40 h-4 rounded mb-2" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex justify-between items-center bg-white/[0.02] rounded-lg px-4 py-3">
            <Bar className="w-32 h-3 rounded" />
            <Bar className="w-10 h-5 rounded" />
          </div>
        ))}
      </div>
    </div>
    <div className="glass-card rounded-lg p-6 space-y-4">
      <Bar className="w-56 h-4 rounded" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="grid grid-cols-5 gap-4 py-3 border-b border-white/5">
          <Bar className="h-4 rounded" />
          <Bar className="h-4 rounded" />
          <Bar className="h-4 rounded" />
          <Bar className="h-4 rounded" />
          <Bar className="h-7 rounded" />
        </div>
      ))}
    </div>
  </div>
);

/* ---------- Customer detail page ---------- */
export const CustomerDetailSkeleton = () => (
  <div className="space-y-6">
    <Bar className="w-40 h-4 rounded" />
    <div className="glass-card rounded-xl p-8">
      <div className="flex flex-col lg:flex-row gap-8">
        <Bar className="w-32 h-32 rounded-full flex-shrink-0" />
        <div className="flex-1 space-y-4">
          <div className="space-y-2">
            <Bar className="w-64 h-8 rounded" />
            <Bar className="w-48 h-3 rounded" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Bar className="w-9 h-9 rounded-lg" />
                <div className="space-y-2 flex-1">
                  <Bar className="w-16 h-3 rounded" />
                  <Bar className="w-24 h-3 rounded" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-5 space-y-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="glass-card rounded-xl p-6 space-y-3">
            <Bar className="w-40 h-4 rounded" />
            <Bar className="h-3 rounded" />
            <Bar className="h-3 rounded w-5/6" />
            <Bar className="h-3 rounded w-4/6" />
          </div>
        ))}
      </div>
      <div className="lg:col-span-3 glass-card rounded-xl p-6 space-y-3">
        <Bar className="w-32 h-4 rounded" />
        {Array.from({ length: 4 }).map((_, i) => (
          <Bar key={i} className="h-12 rounded-lg" />
        ))}
      </div>
      <div className="lg:col-span-4 glass-card rounded-xl p-6 space-y-3">
        <Bar className="w-32 h-4 rounded" />
        {Array.from({ length: 5 }).map((_, i) => (
          <Bar key={i} className="h-10 rounded" />
        ))}
      </div>
    </div>
  </div>
);
