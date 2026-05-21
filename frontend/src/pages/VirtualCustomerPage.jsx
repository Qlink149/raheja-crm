import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Search,
  Filter,
  ChevronRight,
  Wallet,
  MapPin,
  Crown,
  Target,
  Users,
  Flame,
  Snowflake,
  Sun,
  Building2,
  CheckCircle,
  TrendingDown,
} from "lucide-react";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import EmptyState from "../components/feedback/EmptyState";
import { LeadGridSkeleton } from "../components/feedback/Skeletons";
import { api, campaignsAPI } from "../lib/api";
import { DASHBOARD_BUCKET_LABELS } from "../lib/adapters/dashboardAdapter";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";

function PlatformSyncBadge({ status }) {
  const s = (status || "pending").toLowerCase();
  if (s === "pushed") {
    return null; // Hide success state to reduce visual noise
  }
  if (s === "failed") {
    return (
      <Badge variant="destructive" className="shrink-0">
        Sync Failed
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className="border-amber-500/30 bg-amber-900/30 text-amber-300 shrink-0"
    >
      Pending
    </Badge>
  );
}

const VirtualCustomerPage = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [projects, setProjects] = useState([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const sentinelRef = useRef(null);
  const PAGE_SIZE = 50;
  
  // Filter states
  const [activeCategory, setActiveCategory] = useState("all");
  const [budgetFilter, setBudgetFilter] = useState(searchParams.get("budget") || "all");
  const [locationFilter, setLocationFilter] = useState(searchParams.get("location") || "all");
  const [vipFilter, setVipFilter] = useState(searchParams.get("vip") === "true");
  const [intentFilter, setIntentFilter] = useState(searchParams.get("intent") || "all");
  const [temperatureFilter, setTemperatureFilter] = useState(searchParams.get("temperature") || "all");
  const [qualificationFilter, setQualificationFilter] = useState(
    searchParams.get("qualification_category") || "all"
  );
  const [projectFilter, setProjectFilter] = useState(searchParams.get("project") || "all");
  const [campaignIdFilter, setCampaignIdFilter] = useState(
    searchParams.get("campaignId") || searchParams.get("campaign") || "all"
  );
  const [dispositionFilter, setDispositionFilter] = useState(
    searchParams.get("disposition") || "all"
  );
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || "all");
  const [assignedRepFilter, setAssignedRepFilter] = useState(
    searchParams.get("assigned_rep") || "all"
  );
  const [dashboardBucketFilter, setDashboardBucketFilter] = useState(
    searchParams.get("dashboard_bucket") || ""
  );
  const [daysFilter, setDaysFilter] = useState(searchParams.get("days") || "");
  const [startDateFilter, setStartDateFilter] = useState(searchParams.get("start_date") || "");
  const [endDateFilter, setEndDateFilter] = useState(searchParams.get("end_date") || "");
  const [uploadBatches, setUploadBatches] = useState([]);

  const [futworkSyncFilter, setFutworkSyncFilter] = useState(() => {
    const fromUrl = searchParams.get("futwork_sync_status");
    if (fromUrl) return fromUrl;
    if (
      searchParams.get("project") ||
      searchParams.get("assigned_rep") ||
      searchParams.get("dashboard_bucket") ||
      searchParams.get("days") ||
      searchParams.get("start_date")
    ) {
      return "all";
    }
    return "pushed";
  });

  useEffect(() => {
    if (searchParams.get("futwork_sync_status")) return;
    const hasDrillDown =
      searchParams.get("project") ||
      searchParams.get("assigned_rep") ||
      searchParams.get("dashboard_bucket") ||
      searchParams.get("days") ||
      searchParams.get("start_date");
    if (!hasDrillDown) {
      const next = new URLSearchParams(searchParams);
      next.set("futwork_sync_status", "pushed");
      setSearchParams(next, { replace: true });
    }
  }, []);

  useEffect(() => {
    setCampaignIdFilter(searchParams.get("campaignId") || searchParams.get("campaign") || "all");
    setDispositionFilter(searchParams.get("disposition") || "all");
    setStatusFilter(searchParams.get("status") || "all");
    setProjectFilter(searchParams.get("project") || "all");
    setQualificationFilter(searchParams.get("qualification_category") || "all");
    setBudgetFilter(searchParams.get("budget") || "all");
    setLocationFilter(searchParams.get("location") || "all");
    setTemperatureFilter(searchParams.get("temperature") || "all");
    setIntentFilter(searchParams.get("intent") || "all");
    setVipFilter(searchParams.get("vip") === "true");
    setAssignedRepFilter(searchParams.get("assigned_rep") || "all");
    setDashboardBucketFilter(searchParams.get("dashboard_bucket") || "");
    setDaysFilter(searchParams.get("days") || "");
    setStartDateFilter(searchParams.get("start_date") || "");
    setEndDateFilter(searchParams.get("end_date") || "");
    const fw = searchParams.get("futwork_sync_status");
    if (fw) {
      setFutworkSyncFilter(fw);
    } else if (
      searchParams.get("project") ||
      searchParams.get("assigned_rep") ||
      searchParams.get("dashboard_bucket") ||
      searchParams.get("days") ||
      searchParams.get("start_date")
    ) {
      setFutworkSyncFilter("all");
    } else {
      setFutworkSyncFilter("pushed");
    }
  }, [searchParams]);

  // Debounce search input 400ms
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery), 400);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    fetchProjects();
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await campaignsAPI.getUploadBatches();
        if (!cancelled) {
          setUploadBatches(Array.isArray(res.data) ? res.data : []);
        }
      } catch (e) {
        console.error("Failed to load upload batches:", e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Reset and reload when filters or debounced search change
  useEffect(() => {
    setLeads([]);
    setPage(0);
    setHasMore(true);
    fetchLeads(0);
  }, [
    budgetFilter,
    locationFilter,
    vipFilter,
    intentFilter,
    temperatureFilter,
    qualificationFilter,
    projectFilter,
    campaignIdFilter,
    dispositionFilter,
    statusFilter,
    assignedRepFilter,
    futworkSyncFilter,
    debouncedSearch,
    dashboardBucketFilter,
    daysFilter,
    startDateFilter,
    endDateFilter,
    searchParams.toString(),
  ]);

  // Infinite scroll observer
  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading && !loadingMore) {
          const nextPage = page + 1;
          setPage(nextPage);
          fetchMore(nextPage);
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, page]);

  const fetchProjects = async () => {
    try {
      const response = await api.get("/projects");
      setProjects(response.data);
    } catch (error) {
      console.error("Error fetching projects:", error);
      toast.error("Couldn't load project list");
    }
  };

  const urlDashboardBucket =
    searchParams.get("dashboard_bucket") || dashboardBucketFilter || "";
  const urlDays = searchParams.get("days") || daysFilter || "";
  const urlStartDate = searchParams.get("start_date") || startDateFilter || "";
  const urlEndDate = searchParams.get("end_date") || endDateFilter || "";
  const buildParams = (skip = 0) => {
    const params = new URLSearchParams();
    const bucket = searchParams.get("dashboard_bucket") || dashboardBucketFilter;
    const days = searchParams.get("days") || daysFilter;
    const startDate = searchParams.get("start_date") || startDateFilter;
    const endDate = searchParams.get("end_date") || endDateFilter;
    const project =
      searchParams.get("project") || (projectFilter !== "all" ? projectFilter : "");

    if (budgetFilter !== "all") params.append("budget_category", budgetFilter);
    if (locationFilter !== "all") params.append("location_category", locationFilter);
    if (!bucket && vipFilter) params.append("vip_only", "true");
    if (intentFilter !== "all") params.append("intent_category", intentFilter);
    if (!bucket && qualificationFilter !== "all") {
      params.append("qualification_category", qualificationFilter);
    }
    if (project && project !== "all") params.append("project", project);
    if (campaignIdFilter !== "all") params.append("campaignId", campaignIdFilter);
    if (dispositionFilter !== "all") params.append("disposition", dispositionFilter);
    if (!bucket && statusFilter !== "all") params.append("status", statusFilter);
    if (assignedRepFilter !== "all") params.append("assigned_rep", assignedRepFilter);
    if (debouncedSearch) params.append("search", debouncedSearch);

    if (bucket) {
      params.append("dashboard_bucket", bucket);
      params.append("futwork_sync_status", "all");
    } else if (days || startDate) {
      params.append("futwork_sync_status", "all");
    } else if (futworkSyncFilter && futworkSyncFilter !== "all") {
      params.append("futwork_sync_status", futworkSyncFilter);
    }

    if (days) params.append("days", days);
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    params.append("skip", skip);
    params.append("limit", PAGE_SIZE);
    return params;
  };

  const fetchLeads = async (pageNum = 0) => {
    setLoading(true);
    try {
      const params = buildParams(pageNum * PAGE_SIZE);
      const countParams = new URLSearchParams(params);
      countParams.delete("skip");
      countParams.delete("limit");

      const [leadsRes, countRes] = await Promise.allSettled([
        api.get(`/leads?${params.toString()}`),
        api.get(`/leads/count/all?${countParams.toString()}`),
      ]);

      if (leadsRes.status === "fulfilled") {
        const data = leadsRes.value.data || [];
        setLeads(data);
        setHasMore(data.length === PAGE_SIZE);
      } else {
        setLeads([]);
        setHasMore(false);
      }
      if (countRes.status === "fulfilled") {
        setTotalCount(countRes.value.data.count || 0);
      }
    } catch (error) {
      console.error("Error fetching leads:", error);
      toast.error("Couldn't load leads. Try refreshing.");
      setLeads([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchMore = async (pageNum) => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      const params = buildParams(pageNum * PAGE_SIZE);
      const res = await api.get(`/leads?${params.toString()}`);
      const data = res.data || [];
      setLeads((prev) => [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } catch (error) {
      console.error("Error loading more:", error);
    } finally {
      setLoadingMore(false);
    }
  };

  const handleCategoryChange = (category) => {
    setActiveCategory(category);
    // Reset filters when changing category
    if (category === "budget") {
      setLocationFilter("all");
      setVipFilter(false);
      setIntentFilter("all");
      setProjectFilter("all");
    } else if (category === "location") {
      setBudgetFilter("all");
      setVipFilter(false);
      setIntentFilter("all");
      setProjectFilter("all");
    } else if (category === "vip") {
      setBudgetFilter("all");
      setLocationFilter("all");
      setIntentFilter("all");
      setProjectFilter("all");
      setVipFilter(true);
    } else if (category === "intent") {
      setBudgetFilter("all");
      setLocationFilter("all");
      setVipFilter(false);
      setProjectFilter("all");
    } else if (category === "project") {
      setBudgetFilter("all");
      setLocationFilter("all");
      setVipFilter(false);
      setIntentFilter("all");
    } else {
      setBudgetFilter("all");
      setLocationFilter("all");
      setVipFilter(false);
      setIntentFilter("all");
      setTemperatureFilter("all");
      setProjectFilter("all");
    }
  };

  const getInitials = (name) => {
    if (!name || name === "Unknown" || name === "") return "?";
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  // Helper to display value or "Unknown"
  const getDisplayName = (name) => {
    if (!name || name === "" || name === "Unknown") return "Unknown";
    return name;
  };

  const getTemperatureIcon = (temp) => {
    switch (temp) {
      case "Hot":
        return <Flame className="w-4 h-4 text-red-400" />;
      case "Warm":
        return <Sun className="w-4 h-4 text-[#C5A059]" />;
      case "Cold":
        return <Snowflake className="w-4 h-4 text-blue-400" />;
      default:
        return null;
    }
  };

  const getQualificationBadgeClass = (qc) => {
    const v = (qc || "").trim();
    if (v === "VIP Pipeline") return "bg-purple-500/20 text-purple-300 border border-purple-500/30";
    if (v === "Dormant") return "bg-orange-500/20 text-orange-300 border border-orange-500/30";
    if (v === "Qualified") return "bg-emerald-900/30 text-emerald-300 border border-emerald-500/30";
    if (v === "Hot") return "badge-hot";
    if (v === "Cold") return "badge-cold";
    if (v === "all") return "bg-[#C5A059] text-black";
    return "text-[#A3A3A3] bg-white/5 border border-white/5";
  };

  const isNonContactableStatus = (status) => {
    const s = (status || "").trim().toLowerCase().replace(/\s+/g, " ");
    return (
      /^non[\s-]*contactable$/.test(s) ||
      s === "lost" ||
      s === "dnc" ||
      s === "do not call" ||
      s === "not reachable"
    );
  };

  /** Primary card tag: qualification hierarchy (not legacy temperature). */
  const getLeadQualificationTag = (lead) => {
    if (isNonContactableStatus(lead?.status)) return "";
    return (lead?.qualification_category || "").trim();
  };

  const getQualificationIcon = (qc) => {
    switch (qc) {
      case "Hot":
        return <Flame className="w-4 h-4 text-red-400" />;
      case "Cold":
        return <Snowflake className="w-4 h-4 text-blue-400" />;
      case "Qualified":
        return <CheckCircle className="w-4 h-4 text-emerald-400" />;
      case "VIP Pipeline":
        return <Crown className="w-4 h-4 text-[#C5A059]" />;
      case "Dormant":
        return <TrendingDown className="w-4 h-4 text-orange-400" />;
      default:
        return null;
    }
  };

  const getTemperatureBadgeClass = (temp) => {
    switch (temp) {
      case "Hot":
        return "badge-hot";
      case "Warm":
        return "badge-warm";
      case "Cold":
        return "badge-cold";
      default:
        return "";
    }
  };

  // ------ Budget display helpers ------
  // Prefer the canonical `budget_category` bucket; fall back to a formatted
  // numeric `budget` only when the bucket is empty or "Other". Keeps the
  // API contract intact while showing the truthful classification.
  const formatBudgetLabel = (lead) => {
    const bucket = (lead?.budget_category || "").trim();
    if (bucket && bucket !== "Other") return bucket;

    const raw = lead?.budget;
    if (raw == null || raw === "" || raw === "0" || raw === 0) {
      return "Budget N/A";
    }
    const num = Number(raw);
    if (Number.isFinite(num) && num > 0) {
      return `₹${num} Cr`;
    }
    return String(raw);
  };

  const isHniBudget = (lead) => {
    const bucket = (lead?.budget_category || "").trim();
    return bucket === "5 Cr+" || bucket === "2-5 Cr";
  };

  const categories = [
    { id: "all", label: "All Leads", icon: Users },
    { id: "budget", label: "Budget Sensitive", icon: Wallet },
    { id: "location", label: "Location Sensitive", icon: MapPin },
    { id: "project", label: "Project Based", icon: Building2 },
    { id: "vip", label: "VIP / HNI", icon: Crown },
    { id: "intent", label: "Intent Based", icon: Target },
  ];

  const budgetOptions = ["all", "<1 Cr", "1-2 Cr", "2-5 Cr", "5 Cr+"];
  const locationOptions = ["all", "South Mumbai", "Thane", "Bandra/BKC", "Suburbs", "Other"];
  const intentOptions = ["all", "Investor", "Home Seeker"];
  const qualificationOptions = ["all", "Qualified", "VIP Pipeline", "Hot", "Cold", "Dormant"];

  const handleFutworkSyncChange = (value) => {
    setFutworkSyncFilter(value);
    const next = new URLSearchParams(searchParams);
    if (value === "all") {
      next.delete("futwork_sync_status");
    } else {
      next.set("futwork_sync_status", value);
    }
    setSearchParams(next, { replace: true });
  };

  const handleUploadBatchChange = (value) => {
    setCampaignIdFilter(value);
    const next = new URLSearchParams(searchParams);
    if (value === "all") {
      next.delete("campaignId");
    } else {
      next.set("campaignId", value);
    }
    setSearchParams(next, { replace: true });
  };

  const clearDashboardDrill = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("dashboard_bucket");
    next.delete("days");
    next.delete("start_date");
    next.delete("end_date");
    setSearchParams(next, { replace: true });
  };

  const dashboardDrillLabel =
    DASHBOARD_BUCKET_LABELS[urlDashboardBucket] ||
    DASHBOARD_BUCKET_LABELS[dashboardBucketFilter] ||
    "All Leads";

  return (
    <motion.div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <p className="text-[#C5A059] text-sm font-medium tracking-widest uppercase">Lead Explorer</p>
        <h1 className="font-serif text-3xl text-white" data-testid="virtual-customer-title">
          Virtual Customer Explorer
        </h1>
        <p className="text-[#A1A1AA] mt-1">
          {totalCount > 0 ? `${totalCount.toLocaleString()} leads in pipeline` : "Browse and filter your lead pipeline"}
        </p>
        {(urlDashboardBucket || urlDays || urlStartDate) && (
          <div
            className="mt-3 flex flex-wrap items-center gap-2"
            data-testid="dashboard-drill-banner"
          >
            <Badge
              variant="outline"
              className="border-[#C5A059]/40 bg-[#C5A059]/10 text-[#C5A059]"
            >
              Dashboard: {dashboardDrillLabel}
              {urlDays ? ` · ${urlDays} days` : ""}
              {urlStartDate && urlEndDate
                ? ` · ${urlStartDate} – ${urlEndDate}`
                : urlStartDate
                  ? ` · from ${urlStartDate}`
                  : ""}
            </Badge>
            <button
              type="button"
              onClick={clearDashboardDrill}
              className="text-xs text-[#A1A1AA] hover:text-white underline"
            >
              Clear dashboard filter
            </button>
          </div>
        )}
        <motion.div className="mt-4 inline-flex rounded-lg border border-white/10 bg-[#141414] p-1">
          <button
            type="button"
            data-testid="futwork-filter-pushed"
            onClick={() => handleFutworkSyncChange("pushed")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
              futworkSyncFilter === "pushed"
                ? "bg-[#C5A059] text-black"
                : "text-[#A3A3A3] hover:text-white"
            }`}
          >
            Futwork Called
          </button>
          <button
            type="button"
            data-testid="futwork-filter-pending"
            onClick={() => handleFutworkSyncChange("pending")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
              futworkSyncFilter === "pending"
                ? "bg-[#C5A059] text-black"
                : "text-[#A3A3A3] hover:text-white"
            }`}
          >
            Pending
          </button>
          <button
            type="button"
            data-testid="futwork-filter-all"
            onClick={() => handleFutworkSyncChange("all")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
              futworkSyncFilter === "all"
                ? "bg-[#C5A059] text-black"
                : "text-[#A3A3A3] hover:text-white"
            }`}
          >
            All
          </button>
        </motion.div>
      </motion.div>

        <motion.div className="flex flex-col lg:flex-row min-h-[70vh] rounded-xl border border-white/10 overflow-hidden">
          {/* Category Panel */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="w-full lg:w-72 border-b lg:border-b-0 lg:border-r border-white/10 bg-[#0A0A0A] p-6"
          >
            <h2 className="font-serif text-xl text-white mb-6">Categories</h2>

            {/* Category Buttons */}
            {urlDashboardBucket ? (
              <p className="text-xs text-[#A1A1AA] mb-6 px-1">
                Category filters locked while{" "}
                <span className="text-[#C5A059]">{dashboardDrillLabel}</span> is active.
                Clear dashboard filter to browse by category.
              </p>
            ) : (
              <div className="space-y-2 mb-8">
                {categories.map((cat) => (
                  <button
                    key={cat.id}
                    data-testid={`category-${cat.id}`}
                    onClick={() => handleCategoryChange(cat.id)}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-300 ${
                      activeCategory === cat.id
                        ? "bg-[#C5A059]/20 border border-[#C5A059]/30 text-[#C5A059]"
                        : "text-[#A3A3A3] hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <cat.icon className="w-5 h-5" strokeWidth={1.5} />
                    <span className="text-sm font-medium">{cat.label}</span>
                  </button>
                ))}
              </div>
            )}

            {/* Sub-filters based on category */}
            {!urlDashboardBucket && activeCategory === "budget" && (
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-3">
                  Budget Range
                </p>
                {budgetOptions.map((opt) => (
                  <button
                    key={opt}
                    data-testid={`budget-filter-${opt}`}
                    onClick={() => setBudgetFilter(opt)}
                    className={`w-full text-left px-4 py-2 text-sm rounded transition-all ${
                      budgetFilter === opt
                        ? "bg-[#C5A059] text-black font-medium"
                        : "text-[#A3A3A3] hover:bg-white/5"
                    }`}
                  >
                    {opt === "all" ? "All Budgets" : opt}
                  </button>
                ))}
              </div>
            )}

            {!urlDashboardBucket && activeCategory === "location" && (
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-3">
                  Location
                </p>
                {locationOptions.map((opt) => (
                  <button
                    key={opt}
                    data-testid={`location-filter-${opt}`}
                    onClick={() => setLocationFilter(opt)}
                    className={`w-full text-left px-4 py-2 text-sm rounded transition-all ${
                      locationFilter === opt
                        ? "bg-[#C5A059] text-black font-medium"
                        : "text-[#A3A3A3] hover:bg-white/5"
                    }`}
                  >
                    {opt === "all" ? "All Locations" : opt}
                  </button>
                ))}
              </div>
            )}

            {!urlDashboardBucket && activeCategory === "intent" && (
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-3">
                  Purchase Intent
                </p>
                {intentOptions.map((opt) => (
                  <button
                    key={opt}
                    data-testid={`intent-filter-${opt}`}
                    onClick={() => setIntentFilter(opt)}
                    className={`w-full text-left px-4 py-2 text-sm rounded transition-all ${
                      intentFilter === opt
                        ? "bg-[#C5A059] text-black font-medium"
                        : "text-[#A3A3A3] hover:bg-white/5"
                    }`}
                  >
                    {opt === "all" ? "All Intents" : opt}
                  </button>
                ))}
              </div>
            )}

            {!urlDashboardBucket && activeCategory === "project" && (
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-3">
                  Projects
                </p>
                <ScrollArea className="h-64">
                  <button
                    data-testid="project-filter-all"
                    onClick={() => setProjectFilter("all")}
                    className={`w-full text-left px-4 py-2 text-sm rounded transition-all ${
                      projectFilter === "all"
                        ? "bg-[#C5A059] text-black font-medium"
                        : "text-[#A3A3A3] hover:bg-white/5"
                    }`}
                  >
                    All Projects
                  </button>
                  {projects.map((proj) => (
                    <button
                      key={proj.name}
                      data-testid={`project-filter-${proj.name}`}
                      onClick={() => setProjectFilter(proj.name)}
                      className={`w-full text-left px-4 py-2 text-sm rounded transition-all ${
                        projectFilter === proj.name
                          ? "bg-[#C5A059] text-black font-medium"
                          : "text-[#A3A3A3] hover:bg-white/5"
                      }`}
                    >
                      <span className="block truncate">{proj.name}</span>
                      <span className="text-xs opacity-60">({proj.count} leads)</span>
                    </button>
                  ))}
                </ScrollArea>
              </div>
            )}

            {/* Qualification tag filter */}
            <div className="mt-8 pt-6 border-t border-white/10">
              <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-3">
                Lead Qualification
              </p>
              {urlDashboardBucket ? (
                <p className="text-xs text-[#A1A1AA] px-1">
                  Locked while dashboard filter{" "}
                  <span className="text-[#C5A059]">{dashboardDrillLabel}</span> is active.
                  Clear dashboard filter to change qualification.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {qualificationOptions.map((opt) => (
                    <button
                      key={opt}
                      data-testid={`qc-filter-${opt}`}
                      onClick={() => setQualificationFilter(opt)}
                      className={`px-3 py-1 text-xs rounded-full transition-all ${
                        qualificationFilter === opt
                          ? getQualificationBadgeClass(opt === "all" ? "" : opt)
                          : "bg-white/5 text-[#A3A3A3] hover:bg-white/10"
                      } ${qualificationFilter === opt && opt === "all" ? "bg-[#C5A059] text-black" : ""}`}
                    >
                      {opt === "all" ? "All" : opt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.div>

          {/* Leads Grid */}
          <div className="flex-1 p-6 overflow-hidden">
            {/* Search Header */}
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-4 mb-6"
            >
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                <Input
                  data-testid="lead-search-input"
                  placeholder="Search by name or project..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-12 bg-[#1A1A1A] border-white/10 text-white placeholder:text-[#525252] focus:border-[#C5A059] h-12"
                />
              </div>
              {uploadBatches.length > 0 && (
                <Select value={campaignIdFilter} onValueChange={handleUploadBatchChange}>
                  <SelectTrigger
                    className="w-[220px] bg-[#1A1A1A] border-white/10 text-white h-12"
                    data-testid="upload-batch-filter"
                  >
                    <SelectValue placeholder="All upload batches" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1A1A1A] border-white/10">
                    <SelectItem value="all">All upload batches</SelectItem>
                    {uploadBatches.map((b) => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.name} ({b.count} synced)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <div className="flex items-center gap-2 text-[#A3A3A3]">
                <Users className="w-4 h-4" />
                <span className="text-sm">
                  <span className="text-[#C5A059] font-semibold">{totalCount}</span> leads
                  found
                </span>
              </div>
            </motion.div>

            {/* Leads List */}
            <ScrollArea className="h-[calc(100vh-180px)]">
              {loading ? (
                <div className="pr-4">
                  <LeadGridSkeleton count={9} />
                </div>
              ) : leads.length === 0 ? (
                <EmptyState
                  icon={Users}
                  title="No leads match your filters"
                  description="Try widening your filters or upload a new CSV batch to bring in fresh leads."
                  action={{
                    label: "Reset filters",
                    onClick: () => {
                      setActiveCategory("all");
                      setBudgetFilter("all");
                      setLocationFilter("all");
                      setVipFilter(false);
                      setIntentFilter("all");
                      setTemperatureFilter("all");
                      setQualificationFilter("all");
                      setProjectFilter("all");
                      setSearchQuery("");
                    },
                  }}
                />
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 pr-4">
                  {leads.map((lead) => (
                    <motion.div
                      key={lead.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                      onClick={() => navigate(`/customer/${lead.id}`)}
                      className="glass-card rounded-lg p-5 cursor-pointer group hover-lift"
                      whileHover={{ scale: 1.01 }}
                      data-testid={`lead-card-${lead.id}`}
                    >
                      <div className="flex items-start gap-4">
                        {/* Avatar */}
                        <div className="flex-shrink-0 w-14 h-14 rounded-full bg-gradient-to-br from-[#C5A059] to-[#8A6D3B] flex items-center justify-center text-black font-semibold text-lg">
                          {getInitials(lead.full_name)}
                        </div>

                        {/* Info */}
                        <div className="flex-1 min-w-0 overflow-hidden">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-white font-medium truncate max-w-[140px]" title={getDisplayName(lead.full_name)}>
                              {getDisplayName(lead.full_name)}
                            </h3>
                            {lead.vip_category && (
                              <Crown className="w-4 h-4 text-[#C5A059] flex-shrink-0" />
                            )}
                          </div>
                          <p className="text-[#A3A3A3] text-sm truncate max-w-[180px] mb-2" title={lead.project || "N/A"}>
                            {lead.project || "N/A"}
                          </p>
                          <div className="flex items-center gap-2 flex-wrap">
                            {getLeadQualificationTag(lead) ? (
                              <span
                                className={`px-2 py-0.5 text-xs rounded-sm flex items-center gap-1 flex-shrink-0 ${getQualificationBadgeClass(
                                  getLeadQualificationTag(lead)
                                )}`}
                              >
                                {getQualificationIcon(getLeadQualificationTag(lead))}
                                {getLeadQualificationTag(lead)}
                              </span>
                            ) : null}
                            <PlatformSyncBadge status={lead.futwork_sync_status} />
                            <span
                              className={`text-xs whitespace-nowrap px-2 py-0.5 rounded-sm tabular-nums ${
                                isHniBudget(lead)
                                  ? "badge-hni font-semibold"
                                  : "text-[#A3A3A3] bg-white/5 border border-white/5"
                              }`}
                              data-testid={`lead-budget-${lead.id}`}
                            >
                              {formatBudgetLabel(lead)}
                            </span>
                          </div>
                        </div>

                        {/* Arrow */}
                        <ChevronRight className="w-5 h-5 text-[#525252] group-hover:text-[#C5A059] transition-colors flex-shrink-0" />
                      </div>

                      {/* Status Bar */}
                      <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between">
                        <span
                          className={`text-xs px-2 py-1 rounded ${
                            lead.status === "Qualified"
                              ? "bg-emerald-900/30 text-emerald-300"
                              : lead.status === "Open"
                              ? "bg-[#C5A059]/20 text-[#C5A059]"
                              : "bg-red-900/30 text-red-300"
                          }`}
                        >
                          {lead.status || "—"}
                        </span>
                        <span className="text-[#525252] text-xs">
                          {lead.location_category}
                        </span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}

              {/* Infinite scroll sentinel */}
              <div ref={sentinelRef} className="h-8" />
              {loadingMore && (
                <div className="flex justify-center py-4">
                  <div className="w-6 h-6 border-2 border-[#C5A059] border-t-transparent rounded-full animate-spin" />
                </div>
              )}
              {!hasMore && leads.length > 0 && (
                <p className="text-center text-[#525252] text-xs py-4">All {totalCount} leads loaded</p>
              )}
            </ScrollArea>
          </div>
        </motion.div>
    </motion.div>
  );
};

export default VirtualCustomerPage;
