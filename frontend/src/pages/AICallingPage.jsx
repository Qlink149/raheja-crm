import { useState, useEffect, useRef, useMemo, useCallback, memo } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Phone,
  PhoneCall,
  Clock,
  User,
  Play,
  Pause,
  Filter,
  Search,
  FileText,
  CheckCircle,
  XCircle,
  AlertCircle,
  PhoneOff,
  PhoneMissed,
  Sparkles,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { parseCallTranscriptTurns, WHITELABEL_AGENT_LABEL } from "../utils/callTranscript";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import EmptyState from "../components/feedback/EmptyState";
import { CallTableSkeleton } from "../components/feedback/Skeletons";
import { api } from "../lib/api";

const PAGE_SIZE = 50;
const ROW_HEIGHT = 64; // px, matches the grid row's effective height

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

const formatDate = (dateStr) => {
  if (!dateStr) return "N/A";
  const date = new Date(dateStr);
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const DISPOSITION_STYLES = {
  Interested: "bg-emerald-900/30 text-emerald-300 border-emerald-500/30",
  "Semi-Interested": "bg-cyan-900/30 text-cyan-300 border-cyan-500/30",
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
        className="grid grid-cols-7 gap-2 px-4 py-3 hover:bg-white/5 cursor-pointer transition-colors duration-200 items-center border-b border-white/5"
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
        <span className="text-[#A3A3A3] text-sm tabular-nums truncate">
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
      className="glass-card rounded-xl p-6 hover-lift"
    >
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-3 ${t.iconBg} rounded-lg flex-shrink-0`}>
          <Icon className={`w-5 h-5 ${t.iconColor}`} />
        </div>
        <span className={`kicker ${t.labelColor} whitespace-nowrap`}>{label}</span>
      </div>
      <p className="text-3xl font-display text-white tabular-nums">{value}</p>
    </motion.div>
  );
});

// -----------------------------------------------------------------------------
// Main page
// -----------------------------------------------------------------------------
const AICallingPage = () => {
  const [searchParams] = useSearchParams();
  const [calls, setCalls] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [statusOptions, setStatusOptions] = useState([]);
  const [dispositionOptions, setDispositionOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState("all");
  const [selectedCall, setSelectedCall] = useState(null);
  const [showCallDetail, setShowCallDetail] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dispositionFilter, setDispositionFilter] = useState(
    searchParams.get("disposition") || "all"
  );
  const [uploadBatchFilter, setUploadBatchFilter] = useState(
    searchParams.get("upload_batch_id") || searchParams.get("campaignId") || "all"
  );
  const [uploadBatches, setUploadBatches] = useState([]);
  const [updatingDisposition, setUpdatingDisposition] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [summary, setSummary] = useState(null);
  const [aiBatchSummary, setAiBatchSummary] = useState(null);

  // Audio player state
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const audioRef = useRef(null);

  // Virtual list scroll container
  const scrollContainerRef = useRef(null);

  // -------- URL deep-link bootstrap --------
  useEffect(() => {
    const q = searchParams.get("q") || searchParams.get("phone") || "";
    const leadId = searchParams.get("leadId");
    if (q) setSearchQuery(q);
    if (searchParams.get("disposition")) setDispositionFilter(searchParams.get("disposition"));
  }, [searchParams]);

  // -------- Debounced search --------
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery), 400);
    return () => clearTimeout(t);
  }, [searchQuery]);

  // -------- Bootstrap filters --------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [filRes, campRes] = await Promise.allSettled([
          api.get("/call-history/filters"),
          api.get("/campaigns/current"),
        ]);
        if (cancelled) return;
        if (filRes.status === "fulfilled") {
          const d = filRes.value.data || {};
          setCampaigns(Array.isArray(d.campaigns) ? d.campaigns : []);
          setStatusOptions(Array.isArray(d.statuses) ? d.statuses : []);
          setDispositionOptions(Array.isArray(d.dispositions) ? d.dispositions : []);
          setUploadBatches(Array.isArray(d.upload_batches) ? d.upload_batches : []);
        }
        // currentCampaign isn't used in render today but the fetch is kept
        // identical to avoid changing API behavior.
        void campRes;
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
    }),
    [selectedCampaign, statusFilter, dispositionFilter, debouncedSearch, uploadBatchFilter, searchParams]
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
    }),
    [selectedCampaign, statusFilter, dispositionFilter, debouncedSearch, uploadBatchFilter]
  );

  // -------- Primary fetch on filter change --------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setPage(1);
      try {
        const [listRes, sumRes, aiSumRes] = await Promise.all([
          api.get("/call-history", { params: listParams(1) }),
          api.get("/call-history/summary", { params: summaryParams() }),
          api.get("/call-history/ai-batch-summary", { params: summaryParams() }),
        ]);
        if (cancelled) return;
        setCalls(listRes.data?.calls || []);
        setTotal(Number(listRes.data?.total ?? 0));
        setHasMore(Boolean(listRes.data?.has_more));
        setPage(1);
        setSummary(sumRes.data || null);
        setAiBatchSummary(aiSumRes.data?.batch_summary || null);
      } catch (error) {
        console.error("Error fetching call history:", error);
        toast.error("Failed to load call history");
        setCalls([]);
        setTotal(0);
        setHasMore(false);
        setSummary(null);
        setAiBatchSummary(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [listParams, summaryParams]);

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

  // -------- Audio player --------
  const handlePlayPause = useCallback(() => {
    if (audioRef.current) {
      if (isPlaying) audioRef.current.pause();
      else audioRef.current.play();
      setIsPlaying(!isPlaying);
    }
  }, [isPlaying]);

  const handleTimeUpdate = useCallback(() => {
    if (audioRef.current) setAudioProgress(audioRef.current.currentTime);
  }, []);

  const handleLoadedMetadata = useCallback(() => {
    if (audioRef.current) setAudioDuration(audioRef.current.duration);
  }, []);

  const handleSeek = useCallback(
    (e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const percent = (e.clientX - rect.left) / rect.width;
      if (audioRef.current) audioRef.current.currentTime = percent * audioDuration;
    },
    [audioDuration]
  );

  const handleSelectCall = useCallback((call) => {
    setSelectedCall(call);
    setShowCallDetail(true);
    setIsPlaying(false);
    setAudioProgress(0);
  }, []);

  const updateDisposition = useCallback(
    async (call, newDisposition) => {
      if (!call?.lead_id) return;
      setUpdatingDisposition(true);
      try {
        await api.patch(`/leads/${call.lead_id}/disposition`, {
          disposition: newDisposition,
        });
        toast.success(`Marked as ${newDisposition}`);
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
      } catch (err) {
        toast.error(err?.response?.data?.detail || "Failed to update disposition");
      } finally {
        setUpdatingDisposition(false);
      }
    },
    []
  );

  // -------- Memoized derived values --------
  const stats = useMemo(
    () => ({
      total: Number(summary?.total_calls ?? total ?? 0),
      completed: Number(summary?.completed ?? 0),
      interested: Number(summary?.interested ?? 0),
      semiInterested: Number(summary?.semi_interested ?? 0),
      avgDuration: Number(summary?.avg_duration_seconds ?? 0),
    }),
    [summary, total]
  );

  const aiStats = useMemo(
    () => ({
      total: Number(aiBatchSummary?.total_calls ?? 0),
      hot: Number(aiBatchSummary?.hot_leads ?? 0),
      semi: Number(aiBatchSummary?.semi_interested ?? 0),
      mild: Number(aiBatchSummary?.mildly_interested ?? 0),
      not: Number(aiBatchSummary?.not_interested ?? 0),
      voicemail: Number(aiBatchSummary?.voicemail_wrong_number ?? 0),
      bought: Number(aiBatchSummary?.already_bought ?? 0),
      incorrect: Number(aiBatchSummary?.system_tags_incorrect ?? 0),
    }),
    [aiBatchSummary]
  );

  const aiBuckets = useMemo(
    () => [
      { label: "Hot", value: aiStats.hot },
      { label: "Semi", value: aiStats.semi },
      { label: "Mild", value: aiStats.mild },
      { label: "Not Interested", value: aiStats.not },
      { label: "Voicemail/Wrong #", value: aiStats.voicemail },
      { label: "Already Bought", value: aiStats.bought },
    ],
    [aiStats]
  );

  const fallbackStatuses = ["completed", "no-answer", "busy", "failed"];
  const fallbackDispositions = [
    "Interested",
    "Semi-Interested",
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
            Live record of every AI-placed call for Rustomjee campaigns
          </p>
        </motion.div>

        {loading ? (
          <CallTableSkeleton />
        ) : (
          <>
            {/* Stats Cards */}
            <div className="glass-card rounded-lg p-4 mb-8">
            <motion.div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
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
                label="Semi-Interested"
                value={stats.semiInterested}
                tone="cyan"
                delay={0.15}
              />
              <StatTile
                icon={Clock}
                label="Avg Duration"
                value={formatDuration(stats.avgDuration)}
                tone="purple"
                delay={0.2}
              />
            </motion.div>
            </div>

            {/* Batch Summary (AI Structured Extraction) */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className="glass-card rounded-xl p-5 mb-6"
            >
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <h2 className="kicker">Batch Summary (AI Validated)</h2>
                  <p className="text-xs text-[#A3A3A3] mt-1.5">
                    Based on structured extraction from transcripts.{" "}
                    {aiStats.total
                      ? `${aiStats.total} calls analyzed.`
                      : "No AI extractions yet for these filters."}
                  </p>
                </div>
                {aiStats.incorrect > 0 && (
                  <span className="text-xs px-2 py-1 rounded border border-red-500/30 bg-red-900/20 text-red-300">
                    {aiStats.incorrect} system tags incorrect
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mt-4">
                {aiBuckets.map((x) => (
                  <div
                    key={x.label}
                    className="rounded-lg border border-white/10 bg-white/5 p-3 transition-colors duration-300 hover:border-[#C5A059]/30"
                  >
                    <p className="text-[10px] uppercase tracking-widest text-[#737373]">
                      {x.label}
                    </p>
                    <p className="text-xl font-display text-white tabular-nums mt-1">
                      {x.value}
                    </p>
                  </div>
                ))}
              </div>

              {Array.isArray(aiBatchSummary?.top_priority_leads) &&
                aiBatchSummary.top_priority_leads.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-white/10">
                    <p className="kicker mb-2">Top priority leads to call first</p>
                    <ul className="space-y-1 text-sm text-white">
                      {aiBatchSummary.top_priority_leads.map((s) => (
                        <li key={s} className="flex items-center gap-2">
                          <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#C5A059]" />
                          <span className="break-all">{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
            </motion.div>

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
                          {b.name} ({b.count})
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

                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                  <Input
                    placeholder="Search by name or phone..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
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
              className="glass-card rounded-xl overflow-hidden"
            >
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white tracking-tight">
                    Call History
                  </h2>
                  <p className="text-sm text-[#A3A3A3]">
                    <span className="tabular-nums">{total.toLocaleString()}</span> calls
                    found
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

              {/* Header row */}
              <div className="grid grid-cols-7 gap-2 px-4 py-3 bg-[#141414] border-b border-white/10">
                {["Customer", "Phone", "Timestamp", "Duration", "Disposition", "Status", "Action"].map(
                  (h) => (
                    <span
                      key={h}
                      className="text-[11px] uppercase tracking-widest text-[#C5A059] font-semibold"
                    >
                      {h}
                    </span>
                  )
                )}
              </div>

              {/* Virtualized rows */}
              {calls.length === 0 ? (
                <EmptyState
                  icon={PhoneOff}
                  title="No calls match these filters"
                  description="Adjust filters or wait for the next live batch."
                  action={{ label: "Reset filters", onClick: handleResetFilters }}
                />
              ) : (
                <div
                  ref={scrollContainerRef}
                  className="overflow-y-auto scrollbar-luxe"
                  style={{ height: 500 }}
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
                          key={call.id ? `${call.id}-${virtualRow.index}` : `idx-${virtualRow.index}`}
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
              )}

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
        )}

        {/* Call Detail Dialog — restructured for proper containment */}
        <Dialog open={showCallDetail} onOpenChange={setShowCallDetail}>
          <DialogContent className="surface-elevated text-white max-w-3xl w-[calc(100vw-2rem)] h-[min(90vh,820px)] p-0 overflow-hidden flex flex-col gap-0">
            {/* Fixed header */}
            <DialogHeader className="px-6 pt-6 pb-4 border-b border-white/10 flex-shrink-0">
              <DialogTitle className="text-white flex items-center gap-3 text-base">
                <PhoneCall className="w-5 h-5 text-[#C5A059]" />
                <span>Call Details</span>
                <span className="text-[#A3A3A3] text-sm font-normal truncate">
                  · {selectedCall?.customer_name || "Unknown"}
                </span>
              </DialogTitle>
            </DialogHeader>

            {/* Single primary scroll body */}
            {selectedCall && (
              <div className="flex-1 min-h-0 overflow-y-auto scrollbar-luxe px-6 py-5 space-y-6">
                {/* Call Summary */}
                <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                  <h3 className="kicker mb-4 flex items-center gap-2">
                    <Phone className="w-4 h-4" />
                    Call Summary
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Status</p>
                      <span
                        className={`px-2 py-1 rounded text-xs inline-flex items-center gap-1 ${getStatusBadge(
                          selectedCall.status
                        )}`}
                      >
                        <StatusIcon status={selectedCall.status} />
                        <span className="capitalize">{selectedCall.status}</span>
                      </span>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Duration</p>
                      <p className="text-[#C5A059] font-medium tabular-nums">
                        {formatDuration(selectedCall.duration)}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Disposition</p>
                      {selectedCall.disposition ? (
                        <span
                          className={`px-2 py-1 rounded text-xs border inline-block truncate max-w-full ${getDispositionBadge(
                            selectedCall.disposition
                          )}`}
                        >
                          {selectedCall.disposition}
                        </span>
                      ) : (
                        <p className="text-[#A3A3A3]">N/A</p>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Call Date</p>
                      <p className="text-white text-sm tabular-nums truncate">
                        {formatDate(selectedCall.created_at)}
                      </p>
                    </div>
                  </div>

                  {/* Disposition quick-toggle */}
                  <div className="mt-4 pt-4 border-t border-white/10 flex flex-wrap items-center gap-2">
                    <span className="text-xs uppercase tracking-wider text-[#525252] mr-2">
                      Re-classify Lead:
                    </span>
                    <Button
                      data-testid="mark-interested-btn"
                      size="sm"
                      disabled={
                        selectedCall.disposition === "Interested" ||
                        updatingDisposition
                      }
                      onClick={() => updateDisposition(selectedCall, "Interested")}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 btn-tactile"
                    >
                      {updatingDisposition ? "..." : "Mark Interested"}
                    </Button>
                    <Button
                      data-testid="mark-not-interested-btn"
                      size="sm"
                      disabled={
                        selectedCall.disposition === "Not Interested" ||
                        updatingDisposition
                      }
                      onClick={() => updateDisposition(selectedCall, "Not Interested")}
                      className="bg-red-700 hover:bg-red-600 text-white disabled:opacity-40 btn-tactile"
                    >
                      {updatingDisposition ? "..." : "Mark Not Interested"}
                    </Button>
                  </div>
                </div>

                {/* Audio Player */}
                {selectedCall.recording_url && (
                  <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                    <h3 className="kicker mb-4 flex items-center gap-2">
                      <Play className="w-4 h-4" />
                      Call Recording
                    </h3>
                    <div className="flex items-center gap-4">
                      <Button
                        size="icon"
                        onClick={handlePlayPause}
                        className="w-12 h-12 rounded-full bg-[#C5A059] hover:bg-[#E5C585] text-black btn-tactile flex-shrink-0"
                      >
                        {isPlaying ? (
                          <Pause className="w-5 h-5" />
                        ) : (
                          <Play className="w-5 h-5 ml-1" />
                        )}
                      </Button>

                      <div className="flex-1 min-w-0">
                        <div
                          className="h-2 bg-white/10 rounded-full cursor-pointer relative overflow-hidden"
                          onClick={handleSeek}
                        >
                          <div
                            className="absolute inset-y-0 left-0 bg-gradient-to-r from-[#C5A059] to-[#E5C585] rounded-full transition-all duration-150"
                            style={{
                              width: `${(audioProgress / audioDuration) * 100 || 0}%`,
                            }}
                          />
                        </div>
                        <div className="flex justify-between mt-1">
                          <span className="text-xs text-[#A3A3A3] tabular-nums">
                            {formatDuration(Math.floor(audioProgress))}
                          </span>
                          <span className="text-xs text-[#A3A3A3] tabular-nums">
                            {formatDuration(Math.floor(audioDuration))}
                          </span>
                        </div>
                      </div>
                    </div>

                    <audio
                      ref={audioRef}
                      src={selectedCall.recording_url}
                      onTimeUpdate={handleTimeUpdate}
                      onLoadedMetadata={handleLoadedMetadata}
                      onEnded={() => setIsPlaying(false)}
                    />
                  </div>
                )}

                {/* Tabs for Details and Transcript */}
                <Tabs defaultValue="details" className="w-full flex flex-col min-h-0">
                  <TabsList className="bg-white/5 border border-white/10 flex-shrink-0">
                    <TabsTrigger
                      value="details"
                      className="data-[state=active]:bg-[#C5A059] data-[state=active]:text-black transition-all duration-300"
                    >
                      Details
                    </TabsTrigger>
                    <TabsTrigger
                      value="transcript"
                      className="data-[state=active]:bg-[#C5A059] data-[state=active]:text-black transition-all duration-300"
                    >
                      Transcript
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="details" className="mt-4">
                    <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="min-w-0">
                          <p className="text-xs text-[#525252] mb-1">Phone Number</p>
                          <p className="text-white font-mono tabular-nums truncate">
                            {selectedCall.phone || "N/A"}
                          </p>
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs text-[#525252] mb-1">Customer Name</p>
                          <p className="text-white truncate">
                            {selectedCall.customer_name || "Unknown"}
                          </p>
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs text-[#525252] mb-1">Lead ID</p>
                          <p className="text-white font-mono text-sm truncate">
                            {selectedCall.lead_id || "N/A"}
                          </p>
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs text-[#525252] mb-1">Campaign</p>
                          <p className="text-white truncate">
                            {selectedCall.campaign || "N/A"}
                          </p>
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs text-[#525252] mb-1">Direction</p>
                          <p className="text-white capitalize">
                            {selectedCall.direction || "Outbound"}
                          </p>
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs text-[#525252] mb-1">Hangup By</p>
                          <p className="text-white capitalize">
                            {selectedCall.hangup_by || "N/A"}
                          </p>
                        </div>
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="transcript" className="mt-4">
                    <motion.div className="bg-white/5 rounded-lg p-4 border border-white/10 flex flex-col">
                      <h4 className="kicker mb-4 flex flex-shrink-0 items-center gap-2">
                        <FileText className="w-4 h-4" />
                        Call Transcript
                      </h4>
                      {selectedCall.transcript ? (
                        <motion.div className="max-h-[55vh] min-h-[200px] overflow-y-auto pr-1 scrollbar-luxe">
                          <motion.div className="flex flex-col gap-3 w-full pr-2">
                            {parseCallTranscriptTurns(selectedCall.transcript).map((turn, idx) => (
                              <motion.div
                                key={`${idx}-${turn.isUser ? "c" : "a"}-${turn.text.slice(0, 40)}`}
                                className={`flex w-full shrink-0 ${
                                  turn.isUser ? "justify-end" : "justify-start"
                                }`}
                              >
                                <motion.div
                                  className={`max-w-[85%] rounded-lg px-4 py-2 overflow-hidden ${
                                    turn.isUser
                                      ? "bg-white/10 text-white"
                                      : "bg-[#C5A059]/15 text-[#F2D9A8] border border-[#C5A059]/20"
                                  }`}
                                >
                                  <p className="text-xs mb-1 opacity-70">
                                    {turn.isUser ? "Customer" : WHITELABEL_AGENT_LABEL}
                                  </p>
                                  <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
                                    {turn.text}
                                  </p>
                                </motion.div>
                              </motion.div>
                            ))}
                          </motion.div>
                        </motion.div>
                      ) : (
                        <p className="text-[#A3A3A3] text-center py-8">
                          No transcript available for this call
                        </p>
                      )}
                    </motion.div>
                  </TabsContent>
                </Tabs>
              </div>
            )}
          </DialogContent>
        </Dialog>
    </motion.div>
  );
};

export default AICallingPage;
