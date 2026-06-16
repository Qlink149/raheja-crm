import { useState, useEffect, useRef, useMemo, useCallback, memo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Phone,
  PhoneCall,
  Clock,
  User,
  Filter,
  Search,
  CheckCircle,
  XCircle,
  AlertCircle,
  PhoneOff,
  PhoneMissed,
  Sparkles,
  Calendar,
  X,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import CallDetailDialog from "../components/CallDetailDialog";
import { Calendar as CalendarUI } from "../components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import EmptyState from "../components/feedback/EmptyState";
import {
  CallRowSkeleton,
  CallStatsSkeleton,
  CALL_TABLE_GRID_COLS,
} from "../components/feedback/Skeletons";
import LoadingOverlay from "../components/loading/LoadingOverlay";
import { api, campaignsAPI } from "../lib/api";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import {
  buildCallHistoryDateParams,
  formatCallHistoryDateLabel,
  formatDateTimeIST,
} from "../lib/dateUtils";

const PAGE_SIZE = 50;
const ROW_HEIGHT = 64; // px, matches the grid row's effective height
const VISIBLE_ROWS = 15;
const LIST_MIN_HEIGHT = ROW_HEIGHT * VISIBLE_ROWS;

// -----------------------------------------------------------------------------
// Module-scope helpers (pure, never re-allocated per render)
// -----------------------------------------------------------------------------

const formatDuration = (seconds) => {
  if (!seconds) return "0s";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
};

const formatDate = (dateStr) => formatDateTimeIST(dateStr);

const DISPOSITION_STYLES = {
  Interested: "bg-emerald-900/30 text-emerald-300 border-emerald-500/30",
  "Partially Interested": "bg-cyan-900/30 text-cyan-300 border-cyan-500/30",
  "Site Visit": "bg-indigo-900/30 text-indigo-300 border-indigo-500/30",
  "Not Interested": "bg-red-900/30 text-red-300 border-red-500/30",
  Busy: "bg-yellow-900/30 text-yellow-300 border-yellow-500/30",
  Dropped: "bg-orange-900/30 text-orange-300 border-orange-500/30",
  "Incomplete conversation": "bg-gray-900/30 text-gray-300 border-gray-500/30",
};

const STATUS_STYLES = {
  completed: "bg-emerald-900/30 text-emerald-300",
  "no-answer": "bg-yellow-900/30 text-yellow-300",
  busy: "bg-orange-900/30 text-orange-300",
  failed: "bg-red-900/30 text-red-300",
};

const getDispositionBadge = (d) =>
  DISPOSITION_STYLES[d] || "bg-gray-900/30 text-gray-300 border-gray-500/30";

const getStatusBadge = (s) =>
  STATUS_STYLES[s] || "bg-gray-900/30 text-gray-300";

const StatusIcon = ({ status }) => {
  switch (status) {
    case "completed":
      return <CheckCircle className="w-4 h-4" />;
    case "no-answer":
      return <PhoneMissed className="w-4 h-4" />;
    case "busy":
      return <AlertCircle className="w-4 h-4" />;
    case "failed":
      return <XCircle className="w-4 h-4" />;
    default:
      return <Phone className="w-4 h-4" />;
  }
};

// -----------------------------------------------------------------------------
// Memoized CallRow — only re-renders when the row's actual data changes.
// -----------------------------------------------------------------------------
const CallRow = memo(
  function CallRow({ call, onSelect, style }) {
    return (
      <div
        style={style}
        className={`${CALL_TABLE_GRID_COLS} px-4 py-3 hover:bg-white/5 cursor-pointer transition-colors duration-200 items-center border-b border-white/5`}
        onClick={() => onSelect(call)}
      >
        {/* Customer */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#C5A059] to-[#8A6D3B] flex items-center justify-center text-black text-xs font-semibold flex-shrink-0">
            {call.customer_name ? call.customer_name.charAt(0).toUpperCase() : "?"}
          </div>
          <span className="text-white text-sm truncate">
            {call.customer_name || "Unknown"}
          </span>
        </div>

        {/* Phone */}
        <span className="text-[#A3A3A3] text-sm font-mono truncate tabular-nums">
          {call.phone || "N/A"}
        </span>

        {/* Timestamp */}
        <span
          className="text-[#A3A3A3] text-sm tabular-nums whitespace-nowrap"
          title={formatDate(call.created_at)}
        >
          {formatDate(call.created_at)}
        </span>

        {/* Duration */}
        <span className="text-[#C5A059] text-sm font-medium tabular-nums">
          {formatDuration(call.duration)}
        </span>

        {/* Disposition */}
        <div className="min-w-0">
          {call.disposition && (
            <span
              className={`px-2 py-1 rounded text-xs border inline-block truncate max-w-full ${getDispositionBadge(
                call.disposition
              )}`}
            >
              {call.disposition}
            </span>
          )}
        </div>

        {/* Status */}
        <div>
          <span
            className={`px-2 py-1 rounded text-xs flex items-center gap-1 w-fit ${getStatusBadge(
              call.status
            )}`}
          >
            <StatusIcon status={call.status} />
            <span className="capitalize">{call.status}</span>
          </span>
        </div>

        {/* Action */}
        <div>
          <Button
            size="sm"
            variant="ghost"
            className="text-[#C5A059] hover:text-[#E5C585] hover:bg-[#C5A059]/10 btn-tactile"
            onClick={(e) => {
              e.stopPropagation();
              onSelect(call);
            }}
          >
            View Details
          </Button>
        </div>
      </div>
    );
  },
  (prev, next) => {
    const a = prev.call;
    const b = next.call;
    return (
      a.id === b.id &&
      a.disposition === b.disposition &&
      a.status === b.status &&
      a.duration === b.duration &&
      a.customer_name === b.customer_name &&
      a.phone === b.phone &&
      a.created_at === b.created_at &&
      prev.onSelect === next.onSelect
    );
  }
);

// -----------------------------------------------------------------------------
// Stat tile (memoized, no re-render unless value changes)
// -----------------------------------------------------------------------------
const StatTile = memo(function StatTile({
  icon: Icon,
  label,
  value,
  tone = "gold",
  delay = 0,
  title,
}) {
  const toneMap = {
    gold: { iconBg: "bg-[#C5A059]/20", iconColor: "text-[#C5A059]", labelColor: "text-[#C5A059]" },
    emerald: { iconBg: "bg-emerald-900/30", iconColor: "text-emerald-400", labelColor: "text-emerald-400" },
    blue: { iconBg: "bg-blue-900/30", iconColor: "text-blue-400", labelColor: "text-blue-400" },
    cyan: { iconBg: "bg-cyan-900/30", iconColor: "text-cyan-400", labelColor: "text-cyan-400" },
    purple: { iconBg: "bg-purple-900/30", iconColor: "text-purple-400", labelColor: "text-purple-400" },
  };
  const t = toneMap[tone] || toneMap.gold;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="glass-card rounded-xl p-4 sm:p-5 hover-lift min-w-0 overflow-hidden h-full"
      title={title || label}
    >
      <div className={`p-2.5 ${t.iconBg} rounded-lg w-fit mb-3 flex-shrink-0`}>
        <Icon className={`w-5 h-5 ${t.iconColor}`} />
      </div>
      <p
        className={`text-[11px] font-semibold uppercase tracking-wide leading-snug ${t.labelColor} line-clamp-2 break-words`}
      >
        {label}
      </p>
      <p
        className="text-2xl sm:text-3xl font-display text-white tabular-nums mt-2 min-w-0 truncate"
        title={String(value)}
      >
        {value}
      </p>
    </motion.div>
  );
});

// -----------------------------------------------------------------------------
// Main page
// -----------------------------------------------------------------------------
const AICallingPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [calls, setCalls] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [statusOptions, setStatusOptions] = useState([]);
  const [dispositionOptions, setDispositionOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState("all");
  const [selectedCall, setSelectedCall] = useState(null);
  const [showCallDetail, setShowCallDetail] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, flushSearch] = useDebouncedValue(searchQuery, 400, { minLength: 2 });
  const [statusFilter, setStatusFilter] = useState("all");
  const [dispositionFilter, setDispositionFilter] = useState(
    searchParams.get("disposition") || "all"
  );
  const [uploadBatchFilter, setUploadBatchFilter] = useState(
    searchParams.get("upload_batch_id") || searchParams.get("campaignId") || "all"
  );
  const [uploadBatches, setUploadBatches] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [summary, setSummary] = useState(null);
  const [dateRange, setDateRange] = useState(null);

  // Virtual list scroll container
  const scrollContainerRef = useRef(null);

  // -------- URL deep-link bootstrap --------
  useEffect(() => {
    const q = searchParams.get("q") || searchParams.get("phone") || "";
    if (q) setSearchQuery(q);
    if (searchParams.get("disposition")) setDispositionFilter(searchParams.get("disposition"));

    const startDate = searchParams.get("start_date");
    const endDate = searchParams.get("end_date");
    if (startDate) {
      const from = new Date(`${startDate}T12:00:00`);
      const to = new Date(`${(endDate || startDate)}T12:00:00`);
      if (!Number.isNaN(from.getTime()) && !Number.isNaN(to.getTime())) {
        setDateRange({ from, to });
      }
    }
  }, [searchParams]);

  // -------- Bootstrap filters --------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [filRes, batchesRes] = await Promise.allSettled([
          api.get("/call-history/filters"),
          campaignsAPI.getUploadBatches(),
        ]);
        if (cancelled) return;
        if (filRes.status === "fulfilled") {
          const d = filRes.value.data || {};
          setCampaigns(Array.isArray(d.campaigns) ? d.campaigns : []);
          setStatusOptions(Array.isArray(d.statuses) ? d.statuses : []);
          setDispositionOptions(Array.isArray(d.dispositions) ? d.dispositions : []);
        }
        if (batchesRes.status === "fulfilled") {
          setUploadBatches(Array.isArray(batchesRes.value.data) ? batchesRes.value.data : []);
        }
      } catch (e) {
        console.error(e);
        toast.error("Could not load campaign filters");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // -------- Params builders (stable) --------
  const dateParams = useMemo(() => buildCallHistoryDateParams(dateRange), [dateRange]);

  const listParams = useCallback(
    (pageNum) => ({
      page: pageNum,
      size: PAGE_SIZE,
      ...(selectedCampaign && selectedCampaign !== "all" ? { campaign: selectedCampaign } : {}),
      ...(statusFilter && statusFilter !== "all" ? { status: statusFilter } : {}),
      ...(dispositionFilter && dispositionFilter !== "all"
        ? { disposition: dispositionFilter }
        : {}),
      ...(debouncedSearch.trim() ? { q: debouncedSearch.trim() } : {}),
      ...(uploadBatchFilter && uploadBatchFilter !== "all"
        ? { upload_batch_id: uploadBatchFilter }
        : {}),
      ...(searchParams.get("leadId") ? { leadId: searchParams.get("leadId") } : {}),
      ...dateParams,
    }),
    [
      selectedCampaign,
      statusFilter,
      dispositionFilter,
      debouncedSearch,
      uploadBatchFilter,
      searchParams,
      dateParams,
    ]
  );

  const summaryParams = useCallback(
    () => ({
      ...(selectedCampaign && selectedCampaign !== "all" ? { campaign: selectedCampaign } : {}),
      ...(statusFilter && statusFilter !== "all" ? { status: statusFilter } : {}),
      ...(dispositionFilter && dispositionFilter !== "all"
        ? { disposition: dispositionFilter }
        : {}),
      ...(debouncedSearch.trim() ? { q: debouncedSearch.trim() } : {}),
      ...(uploadBatchFilter && uploadBatchFilter !== "all"
        ? { upload_batch_id: uploadBatchFilter }
        : {}),
      ...dateParams,
    }),
    [selectedCampaign, statusFilter, dispositionFilter, debouncedSearch, uploadBatchFilter, dateParams]
  );

  // -------- Primary fetch on filter change --------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setPage(1);
      try {
        const [listRes, sumRes] = await Promise.all([
          api.get("/call-history", { params: listParams(1) }),
          api.get("/call-history/summary", { params: summaryParams() }),
        ]);
        if (cancelled) return;
        setCalls(listRes.data?.calls || []);
        setTotal(Number(listRes.data?.total ?? 0));
        setHasMore(Boolean(listRes.data?.has_more));
        setPage(1);
        setSummary(sumRes.data || null);
        setHasLoadedOnce(true);
      } catch (error) {
        console.error("Error fetching call history:", error);
        toast.error("Failed to load call history");
        if (!hasLoadedOnce) {
          setCalls([]);
          setTotal(0);
          setHasMore(false);
          setSummary(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [listParams, summaryParams, hasLoadedOnce]);

  const isInitialLoading = loading && !hasLoadedOnce;
  const isRefetching = loading && hasLoadedOnce;

  const handleLoadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    const nextPage = page + 1;
    setLoadingMore(true);
    try {
      const res = await api.get("/call-history", { params: listParams(nextPage) });
      const nextCalls = res.data?.calls || [];
      setCalls((prev) => [...prev, ...nextCalls]);
      setPage(nextPage);
      setHasMore(Boolean(res.data?.has_more));
    } catch (e) {
      console.error(e);
      toast.error("Could not load more calls");
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, hasMore, page, listParams]);

  const handleSelectCall = useCallback((call) => {
    setSelectedCall(call);
    setShowCallDetail(true);
  }, []);

  const handleDispositionChange = useCallback((call, newDisposition) => {
    setCalls((prev) =>
      prev.map((c) =>
        c.lead_id === call.lead_id ? { ...c, disposition: newDisposition } : c
      )
    );
    setSelectedCall((prev) =>
      prev && prev.lead_id === call.lead_id
        ? { ...prev, disposition: newDisposition }
        : prev
    );
  }, []);

  // -------- Memoized derived values --------
  const stats = useMemo(() => {
    if (!summary) return null;
    return {
      total: Number(summary.total_calls ?? total ?? 0),
      completed: Number(summary.completed ?? 0),
      interested: Number(summary.interested ?? 0),
      siteVisit: Number(summary.site_visit ?? 0),
      avgDuration: Number(summary.avg_duration_seconds ?? 0),
    };
  }, [summary, total]);

  const fallbackStatuses = ["completed", "no-answer", "busy", "failed"];
  const fallbackDispositions = [
    "Interested",
    "Partially Interested",
    "Site Visit",
    "Not Interested",
    "Busy",
    "Dropped",
    "Incomplete conversation",
  ];
  const statusList = statusOptions.length ? statusOptions : fallbackStatuses;
  const dispositionList = dispositionOptions.length
    ? dispositionOptions
    : fallbackDispositions;

  const handleResetFilters = useCallback(() => {
    setSelectedCampaign("all");
    setStatusFilter("all");
    setDispositionFilter("all");
    setSearchQuery("");
    setDateRange(null);
  }, []);

  const handleClearDateRange = useCallback(() => {
    setDateRange(null);
  }, []);

  // -------- Virtualizer --------
  const virtualizer = useVirtualizer({
    count: calls.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  return (
    <motion.div className="space-y-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="mb-8"
        >
          <p className="text-[#C5A059] text-sm font-medium tracking-widest uppercase mb-2">Voice AI</p>
          <h1 className="font-serif text-3xl text-white mb-2 tracking-tight">
            AI Calling Engine
          </h1>
          <p className="text-[#A1A1AA]">
            Live record of every AI-placed call for Raheja campaigns
          </p>
        </motion.div>

        <>
            {/* Stats Cards */}
            <div className="relative glass-card rounded-lg p-4 mb-8">
              {isInitialLoading ? (
                <CallStatsSkeleton />
              ) : stats ? (
                <motion.div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 sm:gap-4">
                  <StatTile icon={PhoneCall} label="Total Calls" value={stats.total} tone="gold" />
                  <StatTile
                    icon={CheckCircle}
                    label="Completed"
                    value={stats.completed}
                    tone="emerald"
                    delay={0.05}
                  />
                  <StatTile
                    icon={User}
                    label="Interested"
                    value={stats.interested}
                    tone="blue"
                    delay={0.1}
                  />
                  <StatTile
                    icon={Sparkles}
                    label="Site Visit"
                    value={stats.siteVisit}
                    tone="cyan"
                    delay={0.15}
                  />
                  <StatTile
                    icon={Clock}
                    label="Avg Connected Duration"
                    value={formatDuration(stats.avgDuration)}
                    tone="purple"
                    delay={0.2}
                    title="Average talk time for calls with duration greater than 0"
                  />
                </motion.div>
              ) : null}
              <LoadingOverlay show={isRefetching} />
            </div>

            {/* Filters */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
              className="glass-card rounded-xl p-4 mb-6"
            >
              <div className="flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <Filter className="w-4 h-4 text-[#C5A059]" />
                  <Select value={selectedCampaign} onValueChange={setSelectedCampaign}>
                    <SelectTrigger className="w-[200px] bg-[#1A1A1A] border-white/10 text-white">
                      <SelectValue placeholder="All Campaigns" />
                    </SelectTrigger>
                    <SelectContent className="bg-[#1A1A1A] border-white/10">
                      <SelectItem value="all">All Campaigns</SelectItem>
                      {campaigns.map((campaign) => (
                        <SelectItem key={campaign} value={campaign}>
                          {campaign}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[150px] bg-[#1A1A1A] border-white/10 text-white">
                    <SelectValue placeholder="All Status" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1A1A1A] border-white/10">
                    <SelectItem value="all">All Status</SelectItem>
                    {statusList.map((s) => (
                      <SelectItem key={s} value={s} className="capitalize">
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {uploadBatches.length > 0 && (
                  <Select value={uploadBatchFilter} onValueChange={setUploadBatchFilter}>
                    <SelectTrigger className="w-[220px] bg-[#1A1A1A] border-white/10 text-white">
                      <SelectValue placeholder="All Batches" />
                    </SelectTrigger>
                    <SelectContent className="bg-[#1A1A1A] border-white/10">
                      <SelectItem value="all">All Batches</SelectItem>
                      {uploadBatches.map((b) => (
                        <SelectItem key={b.id} value={b.id}>
                          {b.name} ({b.count} synced)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}

                <Select value={dispositionFilter} onValueChange={setDispositionFilter}>
                  <SelectTrigger className="w-[180px] bg-[#1A1A1A] border-white/10 text-white">
                    <SelectValue placeholder="All Dispositions" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1A1A1A] border-white/10">
                    <SelectItem value="all">All Dispositions</SelectItem>
                    {dispositionList.map((d) => (
                      <SelectItem key={d} value={d}>
                        {d}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="flex items-center gap-2">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        className={
                          dateRange?.from
                            ? "bg-[#C5A059]/10 border-[#C5A059]/40 text-white hover:bg-[#C5A059]/15 min-w-[170px] justify-start gap-2"
                            : "bg-[#1A1A1A] border-white/10 text-[#A3A3A3] hover:bg-white/5 hover:text-white min-w-[170px] justify-start gap-2"
                        }
                      >
                        <Calendar className="w-4 h-4 text-[#C5A059] flex-shrink-0" />
                        <span className="truncate text-sm">
                          {formatCallHistoryDateLabel(dateRange)}
                        </span>
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent
                      className="w-auto p-0 bg-[#1A1A1A] border-white/10"
                      align="start"
                    >
                      <div className="px-3 pt-3 pb-1 border-b border-white/10">
                        <p className="text-xs text-[#A3A3A3]">
                          Pick one day or drag a range. Times use IST.
                        </p>
                      </div>
                      <CalendarUI
                        mode="range"
                        selected={dateRange}
                        onSelect={setDateRange}
                        className="bg-[#1A1A1A] text-white"
                      />
                    </PopoverContent>
                  </Popover>
                  {dateRange?.from && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleClearDateRange}
                      className="h-9 px-3 bg-[#1A1A1A] border-white/10 text-[#A3A3A3] hover:text-white hover:border-red-500/40 hover:bg-red-900/20 gap-1.5"
                      title="Clear date filter"
                    >
                      <X className="w-3.5 h-3.5" />
                      Clear
                    </Button>
                  )}
                </div>

                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                  <Input
                    placeholder="Search by name or phone..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && flushSearch()}
                    className="pl-10 bg-[#1A1A1A] border-white/10 text-white placeholder:text-[#525252] focus-visible:ring-[#C5A059]/40 focus-visible:border-[#C5A059]/40"
                  />
                </div>
              </div>
            </motion.div>

            {/* Call History (Virtualized) */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
              className="relative glass-card rounded-xl overflow-hidden"
            >
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white tracking-tight">
                    Call History
                  </h2>
                  <p className="text-sm text-[#A3A3A3]">
                    {hasLoadedOnce ? (
                      <span className="tabular-nums">{total.toLocaleString()}</span>
                    ) : (
                      <span className="text-[#737373]">—</span>
                    )}{" "}
                    calls
                    found
                    {isRefetching && (
                      <span className="text-[#C5A059] ml-1">(refreshing…)</span>
                    )}
                    {calls.length < total ? (
                      <span className="text-[#737373]">
                        {" "}
                        · showing{" "}
                        <span className="tabular-nums">
                          {calls.length.toLocaleString()}
                        </span>{" "}
                        loaded
                      </span>
                    ) : null}
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <div className="min-w-[1020px]">
                  {/* Header row */}
                  <div className={`${CALL_TABLE_GRID_COLS} px-4 py-3 bg-[#141414] border-b border-white/10`}>
                    {["Customer", "Phone", "Timestamp", "Duration", "Disposition", "Status", "Action"].map(
                      (h) => (
                        <span
                          key={h}
                          className={`text-[11px] uppercase text-[#C5A059] font-semibold whitespace-nowrap${
                            h === "Duration"
                              ? " tracking-wide -translate-x-5"
                              : " tracking-widest"
                          }`}
                        >
                          {h}
                        </span>
                      )
                    )}
                  </div>

                  {isInitialLoading ? (
                    <div>
                      {Array.from({ length: 8 }).map((_, i) => (
                        <CallRowSkeleton key={i} />
                      ))}
                    </div>
                  ) : calls.length === 0 ? (
                    <EmptyState
                      icon={PhoneOff}
                      title="No calls match these filters"
                      description="Adjust filters or wait for the next live batch."
                      action={{ label: "Reset filters", onClick: handleResetFilters }}
                    />
                  ) : (
                    <div className="relative">
                      <div
                        ref={scrollContainerRef}
                        className="overflow-y-auto scrollbar-luxe"
                        style={{
                          height: `max(${LIST_MIN_HEIGHT}px, calc(100vh - 240px))`,
                        }}
                      >
                        <div
                          style={{
                            height: `${totalSize}px`,
                            width: "100%",
                            position: "relative",
                          }}
                        >
                          {virtualItems.map((virtualRow) => {
                            const call = calls[virtualRow.index];
                            return (
                              <CallRow
                                key={
                                  call.id
                                    ? `${call.id}-${virtualRow.index}`
                                    : `idx-${virtualRow.index}`
                                }
                                call={call}
                                onSelect={handleSelectCall}
                                style={{
                                  position: "absolute",
                                  top: 0,
                                  left: 0,
                                  width: "100%",
                                  transform: `translateY(${virtualRow.start}px)`,
                                }}
                              />
                            );
                          })}
                        </div>
                      </div>
                      <LoadingOverlay show={isRefetching} />
                    </div>
                  )}
                </div>
              </div>

              {calls.length > 0 && hasMore && (
                <div className="p-4 flex justify-center border-t border-white/10">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="border-[#C5A059]/40 text-[#C5A059] hover:bg-[#C5A059]/10 btn-tactile"
                  >
                    {loadingMore ? "Loading…" : "Load more"}
                  </Button>
                </div>
              )}
            </motion.div>
        </>

        <CallDetailDialog
          open={showCallDetail}
          onOpenChange={setShowCallDetail}
          call={selectedCall}
          onDispositionChange={handleDispositionChange}
        />
    </motion.div>
  );
};

export default AICallingPage;
