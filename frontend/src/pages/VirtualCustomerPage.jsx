import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
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
  Upload,
  Trash2,
  FileSpreadsheet,
  Loader2,
} from "lucide-react";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { ScrollArea } from "../components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";

const VirtualCustomerPage = ({ onLogout, currentUser }) => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef(null);
  
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [projects, setProjects] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [clearing, setClearing] = useState(false);
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
  const [projectFilter, setProjectFilter] = useState(searchParams.get("project") || "all");

  // Debounce search input 400ms
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery), 400);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    fetchProjects();
  }, []);

  // Reset and reload when filters or debounced search change
  useEffect(() => {
    setLeads([]);
    setPage(0);
    setHasMore(true);
    fetchLeads(0);
  }, [budgetFilter, locationFilter, vipFilter, intentFilter, temperatureFilter, projectFilter, debouncedSearch]);

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
    }
  };

  const buildParams = (skip = 0) => {
    const params = new URLSearchParams();
    if (budgetFilter !== "all") params.append("budget_category", budgetFilter);
    if (locationFilter !== "all") params.append("location_category", locationFilter);
    if (vipFilter) params.append("vip_only", "true");
    if (intentFilter !== "all") params.append("intent_category", intentFilter);
    if (temperatureFilter !== "all") params.append("temperature", temperatureFilter);
    if (projectFilter !== "all") params.append("project", projectFilter);
    if (debouncedSearch) params.append("search", debouncedSearch);
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

  const handleFileUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    
    if (!file.name.endsWith('.csv')) {
      toast.error("Please upload a CSV file");
      return;
    }
    
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await api.post("/leads/upload", formData);

      toast.success(`Successfully uploaded ${response.data.count} leads`);
      fetchLeads();
      fetchProjects();
    } catch (error) {
      console.error("Upload error:", error);
      toast.error(error.response?.data?.detail || "Failed to upload CSV");
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleClearAllLeads = async () => {
    setClearing(true);
    try {
      const response = await api.delete("/leads/clear");
      toast.success(`Cleared ${response.data.deleted_count} leads`);
      setShowClearDialog(false);
      fetchLeads();
      fetchProjects();
    } catch (error) {
      console.error("Clear error:", error);
      toast.error("Failed to clear leads");
    } finally {
      setClearing(false);
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
  const temperatureOptions = ["all", "Hot", "Warm", "Cold"];

  return (
    <div className="flex min-h-screen bg-[#0A0A0A]">
      <Sidebar activePage="virtual-customer" onLogout={onLogout} currentUser={currentUser} />

      {/* Main Content */}
      <main className="flex-1 ml-20 lg:ml-64">
        <div className="flex h-screen">
          {/* Category Panel */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="w-72 border-r border-white/10 bg-[#0A0A0A] p-6"
          >
            <h2 className="font-serif text-xl text-white mb-6">Categories</h2>

            {/* Category Buttons */}
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

            {/* Sub-filters based on category */}
            {activeCategory === "budget" && (
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

            {activeCategory === "location" && (
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

            {activeCategory === "intent" && (
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

            {activeCategory === "project" && (
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

            {/* Temperature Filter */}
            <div className="mt-8 pt-6 border-t border-white/10">
              <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-3">
                Lead Temperature
              </p>
              <div className="flex flex-wrap gap-2">
                {temperatureOptions.map((opt) => (
                  <button
                    key={opt}
                    data-testid={`temp-filter-${opt}`}
                    onClick={() => setTemperatureFilter(opt)}
                    className={`px-3 py-1 text-xs rounded-full transition-all ${
                      temperatureFilter === opt
                        ? opt === "Hot"
                          ? "badge-hot"
                          : opt === "Warm"
                          ? "badge-warm"
                          : opt === "Cold"
                          ? "badge-cold"
                          : "bg-[#C5A059] text-black"
                        : "bg-white/5 text-[#A3A3A3] hover:bg-white/10"
                    }`}
                  >
                    {opt === "all" ? "All" : opt}
                  </button>
                ))}
              </div>
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
              <div className="flex items-center gap-2 text-[#A3A3A3]">
                <Users className="w-4 h-4" />
                <span className="text-sm">
                  <span className="text-[#C5A059] font-semibold">{totalCount}</span> leads
                  found
                </span>
              </div>
              
              {/* CSV Upload Button */}
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                accept=".csv"
                className="hidden"
                data-testid="csv-file-input"
              />
              <Button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="bg-[#C5A059] text-black hover:bg-[#E5C585] flex items-center gap-2"
                data-testid="upload-csv-btn"
              >
                {uploading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
                {uploading ? "Uploading..." : "Upload CSV"}
              </Button>
              
              {/* Clear All Button */}
              <Button
                onClick={() => setShowClearDialog(true)}
                variant="outline"
                className="border-red-500/30 text-red-400 hover:bg-red-900/20 hover:text-red-300 flex items-center gap-2"
                data-testid="clear-all-btn"
              >
                <Trash2 className="w-4 h-4" />
                Clear All
              </Button>
            </motion.div>

            {/* Leads List */}
            <ScrollArea className="h-[calc(100vh-180px)]">
              {loading ? (
                <div className="flex items-center justify-center h-64">
                  <div className="w-8 h-8 border-2 border-[#C5A059] border-t-transparent rounded-full spinner" />
                </div>
              ) : leads.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-64 text-[#525252]">
                  <Users className="w-12 h-12 mb-4" />
                  <p>No leads found matching your criteria</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 pr-4">
                  {leads.map((lead) => (
                    <motion.div
                      key={lead.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.2 }}
                      onClick={() => navigate(`/customer/${lead.id}`)}
                      className="glass-card rounded-lg p-5 cursor-pointer group"
                      whileHover={{
                        scale: 1.02,
                        borderColor: "rgba(197, 160, 89, 0.5)",
                      }}
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
                            <span
                              className={`px-2 py-0.5 text-xs rounded-sm flex items-center gap-1 flex-shrink-0 ${getTemperatureBadgeClass(
                                lead.temperature
                              )}`}
                            >
                              {getTemperatureIcon(lead.temperature)}
                              {lead.temperature}
                            </span>
                            <span className="text-[#525252] text-xs whitespace-nowrap">
                              {lead.budget !== "0" && lead.budget
                                ? `${lead.budget} Cr`
                                : "Budget N/A"}
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
                            lead.lead_status === "Qualified"
                              ? "bg-emerald-900/30 text-emerald-300"
                              : lead.lead_status === "Open"
                              ? "bg-[#C5A059]/20 text-[#C5A059]"
                              : "bg-red-900/30 text-red-300"
                          }`}
                        >
                          {lead.lead_status}
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
        </div>
      </main>

      {/* Clear Confirmation Dialog */}
      <Dialog open={showClearDialog} onOpenChange={setShowClearDialog}>
        <DialogContent className="bg-[#1A1A1A] border-white/10">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <Trash2 className="w-5 h-5 text-red-400" />
              Clear All Leads
            </DialogTitle>
            <DialogDescription className="text-[#A3A3A3]">
              Are you sure you want to remove all virtual customers from the database? 
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setShowClearDialog(false)}
              className="border-white/10 text-white hover:bg-white/5"
            >
              Cancel
            </Button>
            <Button
              onClick={handleClearAllLeads}
              disabled={clearing}
              className="bg-red-600 text-white hover:bg-red-500"
              data-testid="confirm-clear-btn"
            >
              {clearing ? (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="w-4 h-4 mr-2" />
              )}
              {clearing ? "Clearing..." : "Clear All"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default VirtualCustomerPage;
