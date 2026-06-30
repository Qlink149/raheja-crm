import { useState, useEffect, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { toast } from "sonner";
import {
  RefreshCw,
  Upload,
  PhoneCall,
  Package,
  Info,
  Pencil,
  Copy,
  Check,
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import UploadLeadsModal from "../components/UploadLeadsModal";
import LeadUploadDetailsModal from "../components/LeadUploadDetailsModal";
import BulkFutworkPushModal from "../components/BulkFutworkPushModal";
import { UI_COPY } from "../lib/brandLabels";
import EmptyState from "../components/feedback/EmptyState";
import { CampaignSkeleton } from "../components/feedback/Skeletons";
import { api, campaignsAPI, isBackendConfigured } from "../lib/api";
import {
  formatUploadDateIST,
  formatUploadTimeIST,
  formatUploadDateTimeIST,
} from "../lib/dateUtils";

const LEAD_UPLOAD_MAX_MB = 10;
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../components/ui/tooltip";

const LIVE_LABELS = [
  { key: "completed", label: "Completed" },
  { key: "busy", label: "Busy" },
  { key: "no_answer", label: "No-answer" },
  { key: "call_disconnected", label: "Call-disconnected" },
  { key: "failed", label: "Failed" },
];

function statusBadgeVariant(status) {
  const s = (status || "").toLowerCase();
  if (s === "running") return { className: "bg-emerald-600/20 text-emerald-400 border-emerald-500/30", label: "Active" };
  if (s === "scheduled") return { className: "bg-amber-600/20 text-amber-300 border-amber-500/30", label: "Scheduled" };
  if (s === "failed") return { className: "bg-red-600/20 text-red-300 border-red-500/30", label: "Failed" };
  if (s === "completed") return { className: "bg-slate-600/20 text-slate-300 border-slate-500/30", label: "Completed" };
  return { className: "bg-white/10 text-[#A3A3A3] border-white/10", label: status || "Unknown" };
}

const CampaignsPage = () => {
  const navigate = useNavigate();

  const [campaign, setCampaign] = useState(null);
  const [uploadHistory, setUploadHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [refreshingMain, setRefreshingMain] = useState(false);
  const [refreshingLive, setRefreshingLive] = useState(false);
  const [copied, setCopied] = useState(false);
  const [uploadSectionOpen, setUploadSectionOpen] = useState(true);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  const [retryingFailed, setRetryingFailed] = useState(false);
  const [detailsUploadId, setDetailsUploadId] = useState(null);
  const [eligibleFutworkCount, setEligibleFutworkCount] = useState(null);
  const [bulkPushModalOpen, setBulkPushModalOpen] = useState(false);
  const processingIdsRef = useRef(new Set());

  const fetchUploadHistory = useCallback(async () => {
    const res = await api.get("/campaigns/current/upload-history");
    setUploadHistory(Array.isArray(res.data) ? res.data : []);
  }, []);

  const fetchEligibleFutworkCount = useCallback(async () => {
    try {
      const res = await campaignsAPI.getBulkFutworkEligibleCount();
      setEligibleFutworkCount(res.data?.eligible_count ?? 0);
    } catch {
      setEligibleFutworkCount(null);
    }
  }, []);

  const fetchCampaign = useCallback(async (refreshStats) => {
    const q = refreshStats ? { params: { refresh_stats: true } } : {};
    const res = await api.get("/campaigns/current", q);
    setCampaign(res.data);
    setLastUpdatedAt(new Date());
    return res.data;
  }, []);

  const loadAll = useCallback(
    async (opts = { liveOnly: false, refreshStats: false }) => {
      if (!isBackendConfigured()) {
        setError(
          "REACT_APP_BACKEND_URL is not set. Configure it in the frontend environment (e.g. .env) so the app can reach the API."
        );
        setCampaign(null);
        setLoading(false);
        return;
      }
      const { liveOnly, refreshStats } = opts;
      if (liveOnly) {
        setRefreshingLive(true);
        try {
          await fetchCampaign(refreshStats);
        } finally {
          setRefreshingLive(false);
        }
        return;
      }
      setLoading(true);
      setError(null);
      try {
        await fetchCampaign(refreshStats);
        await fetchUploadHistory();
        await fetchEligibleFutworkCount();
      } catch (e) {
        const msg =
          e?.response?.data?.detail ||
          e?.message ||
          "Failed to load campaign";
        setError(typeof msg === "string" ? msg : "Failed to load campaign");
        setCampaign(null);
      } finally {
        setLoading(false);
      }
    },
    [fetchCampaign, fetchUploadHistory, fetchEligibleFutworkCount]
  );

  useEffect(() => {
    if (!isBackendConfigured()) {
      setLoading(false);
      setError(
        "REACT_APP_BACKEND_URL is not set. Configure it in the frontend environment (e.g. .env) so the app can reach the API."
      );
      return;
    }
    loadAll({ refreshStats: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasProcessingUpload = uploadHistory.some((row) => row.status === "processing");

  useEffect(() => {
    if (!hasProcessingUpload || !isBackendConfigured()) return undefined;
    const id = setInterval(async () => {
      try {
        await fetchUploadHistory();
        await fetchEligibleFutworkCount();
      } catch {
        /* ignore poll errors */
      }
    }, 5000);
    return () => clearInterval(id);
  }, [hasProcessingUpload, fetchUploadHistory, fetchEligibleFutworkCount]);

  useEffect(() => {
    const prev = processingIdsRef.current;
    const currentProcessing = new Set(
      uploadHistory.filter((row) => row.status === "processing").map((row) => row.id)
    );
    for (const uploadId of prev) {
      if (currentProcessing.has(uploadId)) continue;
      const row = uploadHistory.find((r) => r.id === uploadId);
      if (!row) continue;
      const label = row.batch_name || row.filename || "Upload";
      if (row.status === "completed") {
        const parts = [];
        if (row.new_leads != null) parts.push(`${row.new_leads} new`);
        if (row.updated_leads != null) parts.push(`${row.updated_leads} updated`);
        if (row.unprocessed) parts.push(`${row.unprocessed} skipped`);
        if (row.futwork_pushed != null) parts.push(`${row.futwork_pushed} synced to calling`);
        toast.success(
          parts.length ? `${label} complete: ${parts.join(", ")}` : `${label} complete`
        );
      } else if (row.status === "failed") {
        toast.error(`${label} failed — open details for more info`);
      }
    }
    processingIdsRef.current = currentProcessing;
  }, [uploadHistory]);

  const handleMainRefresh = async () => {
    setRefreshingMain(true);
    setError(null);
    try {
      await fetchCampaign(false);
      await fetchUploadHistory();
      await fetchEligibleFutworkCount();
      setLastUpdatedAt(new Date());
      toast.success("Refreshed");
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "Refresh failed";
      toast.error(typeof msg === "string" ? msg : "Refresh failed");
    } finally {
      setRefreshingMain(false);
    }
  };

  const handleLiveRefresh = async () => {
    try {
      await loadAll({ liveOnly: true, refreshStats: true });
      setLastUpdatedAt(new Date());
      toast.success("Live stats updated");
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "Refresh failed";
      toast.error(typeof msg === "string" ? msg : "Refresh failed");
    }
  };

  const handleRetryFailedLeads = async () => {
    if (!campaign?.id) return;
    setRetryingFailed(true);
    try {
      const res = await api.post(
        `/campaigns/${encodeURIComponent(campaign.id)}/retry-failed-leads`
      );
      const d = res.data || {};
      toast.success(
        `Retry complete: ${d.succeeded ?? 0} succeeded, ${d.still_failed ?? 0} still failed`
      );
      await fetchCampaign(false);
      await fetchUploadHistory();
      setLastUpdatedAt(new Date());
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "Retry failed";
      toast.error(typeof msg === "string" ? msg : "Retry failed");
    } finally {
      setRetryingFailed(false);
    }
  };

  const handleCopyId = async (id) => {
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      toast.success("Campaign ID copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy to clipboard");
    }
  };

  const handleUploadClick = () => setUploadModalOpen(true);

  const handleFileSubmit = async (file, options = {}) => {
    if (!file) return;
    const { batchName = "" } = options;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const params = {};
      if (batchName.trim()) params.batch_name = batchName.trim();
      const res = await api.post("/leads/upload", formData, {
        params: Object.keys(params).length ? params : undefined,
      });
      const d = res.data || {};
      const label = d.batch_name || batchName.trim() || file.name || "Upload";
      if (d.status === "processing") {
        if (d.upload_id) {
          processingIdsRef.current = new Set([
            ...processingIdsRef.current,
            d.upload_id,
          ]);
        }
        const rows = d.row_count != null ? ` (${d.row_count} rows)` : "";
        toast.success(`${label} started${rows}. Processing in the background.`);
      } else {
        const parts = [];
        if (d.new != null) parts.push(`${d.new} new`);
        if (d.updated != null) parts.push(`${d.updated} updated`);
        if (d.unprocessed) parts.push(`${d.unprocessed} skipped`);
        if (d.futwork_pushed != null) parts.push(`${d.futwork_pushed} synced to calling`);
        if (d.futwork_failed != null && d.futwork_failed > 0) {
          parts.push(`${d.futwork_failed} sync failed`);
        }
        toast.success(
          parts.length ? `Upload complete: ${parts.join(", ")}` : "Upload complete"
        );
      }
      await fetchCampaign(false);
      await fetchUploadHistory();
      await fetchEligibleFutworkCount();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to upload CSV");
      throw e;
    } finally {
      setUploading(false);
    }
  };

  const formatDateTime = (value) => {
    if (!value) return "—";
    try {
      return format(new Date(value), "MMM d, yyyy 'at' hh:mm a");
    } catch {
      return "—";
    }
  };

  const formatClock = (d) => {
    if (!d) return "";
    try {
      return format(d, "hh:mm a");
    } catch {
      return "";
    }
  };

  if (loading) {
    return (
      <motion.div className="space-y-8">

          <CampaignSkeleton />
      </motion.div>
    );
  }

  if (error || !campaign) {
    return (
      <motion.div className="space-y-8">

          <Card className="max-w-xl border-white/10 bg-[#141414] text-white">
            <CardHeader>
              <CardTitle className="text-lg">Campaign unavailable</CardTitle>
            </CardHeader>
            <CardContent className="text-[#A3A3A3] text-sm space-y-2">
              <p>{error || "No campaign data returned."}</p>
              <Button
                variant="outline"
                className="mt-2 border-white/10 text-white hover:bg-white/5"
                onClick={() => loadAll({ refreshStats: false })}
              >
                Retry
              </Button>
            </CardContent>
          </Card>
      </motion.div>
    );
  }

  const badge = statusBadgeVariant(campaign.status);
  const live = campaign.live_status || {};
  // API payloads use futwork_* keys; UI copy stays vendor-neutral.
  const platformId = campaign.futwork_campaign_id || "";

  return (
    <TooltipProvider>
      <motion.div className="space-y-8">

          {/* Header */}
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="page-kicker mb-2">Outreach</p>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="page-title text-2xl sm:text-3xl tracking-tight">
                  {campaign.name || "Campaign"}
                </h1>
                <Badge variant="outline" className={badge.className}>
                  {badge.label}
                </Badge>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-[#A3A3A3]">
                <span>Campaign ID:</span>
                <code className="rounded bg-white/5 px-2 py-0.5 text-xs text-white break-all max-w-[min(100%,28rem)]">
                  {platformId || "—"}
                </code>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-[#C5A059] hover:text-[#E5C585]"
                      onClick={() => handleCopyId(platformId)}
                      disabled={!platformId}
                    >
                      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Copy campaign ID</TooltipContent>
                </Tooltip>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                className="border-white/10 text-white hover:bg-white/5"
                onClick={() => navigate("/ai-calling")}
              >
                <PhoneCall className="h-4 w-4 mr-2" />
                Call History
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
            {/* Campaign Information */}
            <Card className="border-white/10 bg-[#141414] text-white shadow-lg">
              <CardHeader className="flex flex-row items-center gap-2 space-y-0 pb-2">
                <Package className="h-5 w-5 text-[#C5A059]" />
                <CardTitle className="text-base font-semibold">Campaign Information</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 text-sm">
                  <div>
                    <dt className="text-[#737373] flex items-center gap-1">
                      Number of attempts
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button type="button" className="text-[#525252] hover:text-[#A3A3A3]">
                            <Info className="h-3.5 w-3.5" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">
                          From server configuration (PLATFORM_MAX_ATTEMPTS) when set.
                        </TooltipContent>
                      </Tooltip>
                    </dt>
                    <dd className="mt-1 font-medium text-white">
                      {campaign.max_attempts != null ? campaign.max_attempts : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[#737373] flex items-center gap-1">
                      Call rate limit
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button type="button" className="text-[#525252] hover:text-[#A3A3A3]">
                            <Info className="h-3.5 w-3.5" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">
                          From server configuration (PLATFORM_CALL_RATE_LIMIT) when set.
                        </TooltipContent>
                      </Tooltip>
                    </dt>
                    <dd className="mt-1 font-medium text-white">
                      {campaign.call_rate_limit != null ? campaign.call_rate_limit : "—"}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-[#737373]">Agent ID</dt>
                    <dd className="mt-1 font-mono text-xs text-white break-all">
                      {campaign.agent_id || "—"}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-[#737373]">Agent name</dt>
                    <dd className="mt-1 font-medium text-white">{campaign.agent_name || "—"}</dd>
                  </div>
                </dl>
              </CardContent>
              <CardFooter className="flex flex-col items-stretch border-t border-white/10 pt-4 text-sm text-[#A3A3A3] gap-1">
                <div className="flex justify-between gap-4">
                  <span>Created at</span>
                  <span className="text-white text-right">{formatDateTime(campaign.created_at)}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span>Last updated</span>
                  <span className="text-white text-right">{formatDateTime(campaign.updated_at)}</span>
                </div>
              </CardFooter>
            </Card>

            {/* Live Lead Status */}
            <Card className="border-white/10 bg-[#141414] text-white shadow-lg">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-base font-semibold">Live Lead Status</CardTitle>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="border-white/10 text-white hover:bg-white/5"
                  onClick={handleLiveRefresh}
                  disabled={refreshingLive}
                >
                  {refreshingLive ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  <span className="ml-2 hidden sm:inline">Refresh</span>
                </Button>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3 max-w-md mx-auto">
                  {LIVE_LABELS.map(({ key, label }) => (
                    <li
                      key={key}
                      className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3"
                    >
                      <span className="text-[#A3A3A3] text-sm">{label}</span>
                      <span className="text-xl font-semibold text-white tabular-nums">
                        {Number(live[key] ?? 0)}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>

          {/* Lead Upload & History */}
          <Card className="border-white/10 bg-[#141414] text-white shadow-lg">
            <CardHeader
              className="cursor-pointer flex flex-row items-center justify-between space-y-0 pb-2"
              onClick={() => setUploadSectionOpen((o) => !o)}
            >
              <div className="flex items-center gap-2">
                <Upload className="h-5 w-5 text-[#C5A059]" />
                <CardTitle className="text-base font-semibold">Lead Upload &amp; History</CardTitle>
              </div>
              {uploadSectionOpen ? (
                <ChevronUp className="h-5 w-5 text-[#737373]" />
              ) : (
                <ChevronDown className="h-5 w-5 text-[#737373]" />
              )}
            </CardHeader>
            {uploadSectionOpen && (
              <CardContent className="space-y-4">
                <p className="text-sm text-[#A3A3A3]">
                  CSV columns: <span className="text-white">Name</span>,{" "}
                  <span className="text-white">Mobile</span> (required). Optional{" "}
                  <span className="text-white">Lead ID</span> (flexible header names accepted).
                  Each mobile is unique — re-uploading the same number updates the existing lead.
                </p>
                {hasProcessingUpload ? (
                  <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-300" />
                    <span>
                      Upload batch processing in the background — you can leave this page.
                      Progress appears in Recent uploads below.
                    </span>
                  </div>
                ) : null}
                {eligibleFutworkCount != null ? (
                  <p className="text-sm text-[#A3A3A3] rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3">
                    <span className="text-white font-medium tabular-nums">{eligibleFutworkCount}</span>{" "}
                    {UI_COPY.eligiblePushHint}
                  </p>
                ) : null}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap items-center gap-2 text-sm text-[#A3A3A3]">
                    <Clock className="h-4 w-4 text-[#C5A059]" />
                    <span>Recent uploads</span>
                    <Badge variant="secondary" className="bg-white/10 text-[#A3A3A3]">
                      {uploadHistory.length} batch{uploadHistory.length === 1 ? "" : "es"}
                    </Badge>
                    <span className="inline-flex items-center gap-1 text-emerald-400">
                      <Check className="h-4 w-4" />
                      Updated
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      className="border-white/10 text-white hover:bg-white/5"
                      onClick={handleUploadClick}
                      disabled={uploading}
                    >
                      {uploading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Upload className="h-4 w-4 mr-2" />
                      )}
                      {uploading ? "Starting upload…" : "Upload New Leads"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="border-[#C5A059]/40 text-[#C5A059] hover:bg-[#C5A059]/10"
                      onClick={() => setBulkPushModalOpen(true)}
                      disabled={
                        !campaign?.futwork_push_enabled ||
                        eligibleFutworkCount == null ||
                        eligibleFutworkCount < 1
                      }
                    >
                      <PhoneCall className="h-4 w-4 mr-2" />
                      {UI_COPY.pushToCallingEngine}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="border-amber-500/30 text-amber-300 hover:bg-amber-900/20"
                      onClick={handleRetryFailedLeads}
                      disabled={retryingFailed || !campaign?.id}
                    >
                      {retryingFailed ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4 mr-2" />
                      )}
                      Retry Failed Syncs
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="border-white/10 text-white hover:bg-white/5"
                      onClick={handleMainRefresh}
                      disabled={refreshingMain}
                    >
                      {refreshingMain ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                      <span className="ml-2">Refresh</span>
                    </Button>
                  </div>
                </div>

                {uploadHistory.length === 0 ? (
                  <div className="rounded-lg border border-white/10 overflow-hidden">
                    <EmptyState
                      icon={Upload}
                      title="No uploads yet"
                      description="Upload your first CSV batch to start seeing upload history here."
                      action={{
                        label: "Upload first batch",
                        onClick: handleUploadClick,
                        icon: Upload,
                      }}
                    />
                  </div>
                ) : (
                <div className="rounded-lg border border-white/10 overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/10 hover:bg-transparent">
                        <TableHead className="text-[#A3A3A3]">Batch name</TableHead>
                        <TableHead className="text-[#A3A3A3]">Type</TableHead>
                        <TableHead className="text-[#A3A3A3]">Date</TableHead>
                        <TableHead className="text-[#A3A3A3]">Time</TableHead>
                        <TableHead className="text-[#A3A3A3]">Processed</TableHead>
                        <TableHead className="text-[#A3A3A3]">Unprocessed</TableHead>
                        <TableHead className="text-[#A3A3A3] w-[100px]">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {uploadHistory.map((row) => {
                          const dateLabel = formatUploadDateIST(row.created_at);
                          const timeLabel = formatUploadTimeIST(row.created_at);
                          const tooltipLine = [row.filename, formatUploadDateTimeIST(row.created_at)]
                            .filter(Boolean)
                            .join(" • ");
                          return (
                            <TableRow key={row.id} className="border-white/10 hover:bg-white/[0.02]">
                              <TableCell className="text-white font-medium max-w-[180px] truncate">
                                <button
                                  type="button"
                                  className="text-left hover:text-[#C5A059] underline-offset-2 hover:underline truncate max-w-full"
                                  onClick={() =>
                                    navigate(
                                      `/virtual-customer?campaignId=${encodeURIComponent(row.id)}`
                                    )
                                  }
                                >
                                  {row.batch_name || row.filename || "—"}
                                </button>
                              </TableCell>
                              <TableCell>
                                {row.source === "bulk_push" ? (
                                  <Badge className="bg-violet-600/20 text-violet-300 border-violet-500/30">
                                    DB push
                                  </Badge>
                                ) : (
                                  <Badge className="bg-white/10 text-[#A3A3A3] border-white/10">
                                    CSV
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell className="text-white font-medium tabular-nums">
                                {tooltipLine ? (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <span className="cursor-help">{dateLabel}</span>
                                    </TooltipTrigger>
                                    <TooltipContent className="max-w-xs break-all">
                                      {tooltipLine}
                                    </TooltipContent>
                                  </Tooltip>
                                ) : (
                                  dateLabel
                                )}
                              </TableCell>
                              <TableCell className="text-[#A3A3A3] tabular-nums">
                                {timeLabel}
                              </TableCell>
                              <TableCell className="py-3 px-4 text-[#C5A059] font-medium tabular-nums">
                                {row.status === "processing" ? (
                                  <span className="inline-flex items-center gap-2 text-amber-300">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Processing…
                                  </span>
                                ) : (
                                  row.processed ?? 0
                                )}
                              </TableCell>
                              <TableCell className="py-3 px-4">
                                <span className="text-[#A3A3A3] tabular-nums">
                                  {(row.unprocessed || 0) + (row.futwork_failed || 0)}
                                </span>
                                {row.futwork_failed > 0 && (
                                  <span className="ml-2 inline-block text-[10px] text-red-400 bg-red-400/10 px-2 py-0.5 rounded-sm border border-red-500/20">
                                    Includes {row.futwork_failed} Sync Failures
                                  </span>
                                )}
                              </TableCell>
                              <TableCell className="py-3 px-2">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-[#C5A059] hover:text-white hover:bg-white/10"
                                  aria-label="Upload details"
                                  onClick={() => setDetailsUploadId(row.id)}
                                >
                                  <Pencil className="h-4 w-4" />
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                    </TableBody>
                  </Table>
                </div>
                )}
                <p className="text-right text-xs text-[#737373]">
                  Last updated: {formatClock(lastUpdatedAt) || "—"}
                </p>
              </CardContent>
            )}
          </Card>

          <UploadLeadsModal
            open={uploadModalOpen}
            onOpenChange={setUploadModalOpen}
            onSubmit={handleFileSubmit}
            uploading={uploading}
            maxMb={LEAD_UPLOAD_MAX_MB}
          />

          <LeadUploadDetailsModal
            open={Boolean(detailsUploadId)}
            onOpenChange={(open) => {
              if (!open) setDetailsUploadId(null);
            }}
            uploadId={detailsUploadId}
            onUpdated={fetchUploadHistory}
          />

          <BulkFutworkPushModal
            open={bulkPushModalOpen}
            onOpenChange={setBulkPushModalOpen}
            eligibleCount={eligibleFutworkCount ?? 0}
            futworkEnabled={Boolean(campaign?.futwork_push_enabled)}
            onStarted={async () => {
              await fetchUploadHistory();
              await fetchEligibleFutworkCount();
            }}
          />
    </motion.div>
    </TooltipProvider>
  );
};

export default CampaignsPage;
