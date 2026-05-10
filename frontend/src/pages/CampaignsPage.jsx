import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { toast } from "sonner";
import {
  RefreshCw,
  Upload,
  PhoneCall,
  Package,
  Info,
  Copy,
  Check,
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
  Download,
} from "lucide-react";
import Sidebar from "../components/Sidebar";
import UploadLeadsModal from "../components/UploadLeadsModal";
import { api, getApiBase, isBackendConfigured } from "../lib/api";

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

const CampaignsPage = ({ onLogout, currentUser }) => {
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
  const [failedSyncCount, setFailedSyncCount] = useState(0);
  const [retryingFailed, setRetryingFailed] = useState(false);

  const fetchFailedSyncCount = useCallback(async (campaignId) => {
    if (!campaignId || !isBackendConfigured()) {
      setFailedSyncCount(0);
      return;
    }
    try {
      const res = await api.get("/leads/count/all", {
        params: {
          campaign_id: campaignId,
          futwork_sync_status: "failed",
        },
      });
      setFailedSyncCount(Number(res.data?.count ?? 0));
    } catch {
      setFailedSyncCount(0);
    }
  }, []);

  const fetchUploadHistory = useCallback(async () => {
    const res = await api.get("/campaigns/current/upload-history");
    setUploadHistory(Array.isArray(res.data) ? res.data : []);
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
          const data = await fetchCampaign(refreshStats);
          await fetchFailedSyncCount(data?.id);
        } finally {
          setRefreshingLive(false);
        }
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await fetchCampaign(refreshStats);
        await Promise.all([
          fetchUploadHistory(),
          fetchFailedSyncCount(data?.id),
        ]);
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
    [fetchCampaign, fetchUploadHistory, fetchFailedSyncCount]
  );

  useEffect(() => {
    if (campaign?.id) {
      fetchFailedSyncCount(campaign.id);
    } else {
      setFailedSyncCount(0);
    }
  }, [campaign?.id, fetchFailedSyncCount]);

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

  const handleMainRefresh = async () => {
    setRefreshingMain(true);
    setError(null);
    try {
      const data = await fetchCampaign(false);
      await Promise.all([
        fetchUploadHistory(),
        fetchFailedSyncCount(data?.id),
      ]);
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
      const data = await fetchCampaign(false);
      await Promise.all([
        fetchFailedSyncCount(data?.id),
        fetchUploadHistory(),
      ]);
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
    const { pushToFutwork = false } = options;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await api.post("/leads/upload", formData, {
        params: pushToFutwork ? { push_to_futwork: true } : undefined,
      });
      const d = res.data || {};
      const parts = [];
      if (d.new != null) parts.push(`${d.new} new`);
      if (d.updated != null) parts.push(`${d.updated} updated`);
      if (d.unprocessed) parts.push(`${d.unprocessed} skipped`);
      if (pushToFutwork) {
        parts.push(d.futwork_pushed ? "pushed to Futwork" : "Futwork push failed");
      }
      toast.success(
        parts.length ? `Upload complete: ${parts.join(", ")}` : "Upload complete"
      );
      const data = await fetchCampaign(false);
      await Promise.all([
        fetchUploadHistory(),
        fetchFailedSyncCount(data?.id),
      ]);
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

  const formatTableDate = (value) => {
    if (!value) return "—";
    try {
      return format(new Date(value), "d MMM yyyy");
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
      <div className="flex min-h-screen bg-[#0A0A0A]">
        <Sidebar activePage="campaigns" onLogout={onLogout} currentUser={currentUser} />
        <main className="flex-1 flex items-center justify-center ml-20 lg:ml-64 p-8">
          <div className="flex flex-col items-center gap-3 text-[#A3A3A3]">
            <Loader2 className="h-10 w-10 animate-spin text-[#C5A059]" />
            <p>Loading campaign…</p>
          </div>
        </main>
      </div>
    );
  }

  if (error || !campaign) {
    return (
      <div className="flex min-h-screen bg-[#0A0A0A]">
        <Sidebar activePage="campaigns" onLogout={onLogout} currentUser={currentUser} />
        <main className="flex-1 p-8 ml-20 lg:ml-64">
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
        </main>
      </div>
    );
  }

  const badge = statusBadgeVariant(campaign.status);
  const live = campaign.live_status || {};
  const futworkId = campaign.futwork_campaign_id || "";

  return (
    <TooltipProvider>
      <div className="flex min-h-screen bg-[#0A0A0A]">
        <Sidebar activePage="campaigns" onLogout={onLogout} currentUser={currentUser} />

        <main className="flex-1 p-4 sm:p-6 lg:p-8 ml-20 lg:ml-64 space-y-6">
          {/* Header */}
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="font-serif text-2xl sm:text-3xl text-white tracking-tight">
                  {campaign.name || "Campaign"}
                </h1>
                <Badge variant="outline" className={badge.className}>
                  {badge.label}
                </Badge>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-[#A3A3A3]">
                <span>Campaign ID:</span>
                <code className="rounded bg-white/5 px-2 py-0.5 text-xs text-white break-all max-w-[min(100%,28rem)]">
                  {futworkId || "—"}
                </code>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-[#C5A059] hover:text-[#E5C585]"
                      onClick={() => handleCopyId(futworkId)}
                      disabled={!futworkId}
                    >
                      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Copy campaign ID</TooltipContent>
                </Tooltip>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {failedSyncCount > 0 && (
                <Button
                  type="button"
                  variant="outline"
                  className="border-amber-500/30 text-amber-300 hover:bg-amber-900/20"
                  onClick={handleRetryFailedLeads}
                  disabled={retryingFailed}
                >
                  {retryingFailed ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4 mr-2" />
                  )}
                  Retry Failed Leads
                </Button>
              )}
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
                          From server configuration (FUTWORK_MAX_ATTEMPTS) when set.
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
                          From server configuration (FUTWORK_CALL_RATE_LIMIT) when set.
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
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap items-center gap-2 text-sm text-[#A3A3A3]">
                    <Clock className="h-4 w-4 text-[#C5A059]" />
                    <span>Recent uploads</span>
                    <Badge variant="secondary" className="bg-white/10 text-[#A3A3A3]">
                      {uploadHistory.length} entries
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
                      Upload New Leads
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

                <div className="rounded-lg border border-white/10 overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/10 hover:bg-transparent">
                        <TableHead className="text-[#A3A3A3]">Date</TableHead>
                        <TableHead className="text-[#A3A3A3]">Processed</TableHead>
                        <TableHead className="text-[#A3A3A3]">Unprocessed</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {uploadHistory.length === 0 ? (
                        <TableRow className="border-white/10 hover:bg-white/[0.02]">
                          <TableCell colSpan={3} className="text-center text-[#737373] py-10">
                            No uploads yet. Upload a CSV to see history here.
                          </TableCell>
                        </TableRow>
                      ) : (
                        uploadHistory.map((row) => {
                          const unprocessedCount = Number(row.unprocessed ?? 0);
                          const downloadHref = `${getApiBase()}/campaigns/current/upload-history/${encodeURIComponent(
                            row.id
                          )}/unprocessed.csv`;
                          const dateLabel = formatTableDate(row.created_at);
                          const tooltipLine = [row.filename, formatDateTime(row.created_at)]
                            .filter(Boolean)
                            .join(" • ");
                          return (
                            <TableRow key={row.id} className="border-white/10 hover:bg-white/[0.02]">
                              <TableCell className="text-white font-medium">
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
                              <TableCell className="text-emerald-400 font-semibold tabular-nums">
                                {row.processed ?? 0}
                              </TableCell>
                              <TableCell className="font-semibold tabular-nums">
                                {unprocessedCount > 0 ? (
                                  <a
                                    href={downloadHref}
                                    download
                                    className="inline-flex items-center gap-1 text-red-400 hover:text-red-300 hover:underline"
                                    title="Download unprocessed rows"
                                  >
                                    {unprocessedCount}
                                    <Download className="h-4 w-4" />
                                  </a>
                                ) : (
                                  <span className="text-[#737373]">0</span>
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })
                      )}
                    </TableBody>
                  </Table>
                </div>
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
            canPushToFutwork={Boolean(campaign?.futwork_push_enabled)}
          />
        </main>
      </div>
    </TooltipProvider>
  );
};

export default CampaignsPage;
