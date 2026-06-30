import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { toast } from "sonner";
import {
  Flame,
  Snowflake,
  ThermometerSun,
  Users,
  Search,
  ChevronRight,
  Target,
} from "lucide-react";
import { Input } from "../components/ui/input";
import { LeadGridSkeleton, KpiTileSkeleton } from "../components/feedback/Skeletons";
import LoadingOverlay from "../components/loading/LoadingOverlay";
import FetchError from "../components/loading/FetchError";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

const MyDashboardPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState(null);
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [metricsError, setMetricsError] = useState(null);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [hasLoadedLeadsOnce, setHasLoadedLeadsOnce] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, flushSearch] = useDebouncedValue(search, 400, { minLength: 2 });
  const [tempFilter, setTempFilter] = useState("all");

  const loadDashboard = useCallback(async () => {
    setMetricsError(null);
    try {
      const res = await api.get("/my-dashboard");
      setMetrics(res.data?.metrics || {});
    } catch (err) {
      toast.error("Failed to load dashboard metrics");
      setMetricsError(err);
      setMetrics(null);
    }
  }, []);

  const loadLeads = useCallback(async () => {
    setLeadsLoading(true);
    try {
      const params = { skip: 0, limit: 100 };
      if (tempFilter !== "all") params.temperature = tempFilter;
      if (debouncedSearch) params.search = debouncedSearch;
      const res = await api.get("/my-dashboard/leads", { params });
      setLeads(res.data?.leads || []);
      setTotal(res.data?.total || 0);
      setHasLoadedLeadsOnce(true);
    } catch {
      toast.error("Failed to load your leads");
    } finally {
      setLeadsLoading(false);
    }
  }, [debouncedSearch, tempFilter]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await loadDashboard();
      setLoading(false);
    })();
  }, [loadDashboard]);

  useEffect(() => {
    if (!loading) loadLeads();
  }, [loading, loadLeads]);

  const cards = metrics
    ? [
        { label: "My Leads", value: metrics.total_leads ?? 0, icon: Users, color: "text-[#C5A059]" },
        { label: "Hot", value: metrics.hot ?? 0, icon: Flame, color: "text-red-400" },
        { label: "Warm", value: metrics.warm ?? 0, icon: ThermometerSun, color: "text-amber-400" },
        { label: "Cold", value: metrics.cold ?? 0, icon: Snowflake, color: "text-blue-400" },
        { label: "Qualified", value: metrics.qualified ?? 0, icon: Target, color: "text-emerald-400" },
      ]
    : [];

  const isLeadsInitialLoading = leadsLoading && !hasLoadedLeadsOnce;
  const isLeadsRefetching = leadsLoading && hasLoadedLeadsOnce;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <p className="page-kicker mb-1">My Dashboard</p>
        <h1 className="page-title text-3xl">
          Welcome, {user?.full_name?.split(" ")[0] || "Agent"}
        </h1>
        <p className="page-subtitle text-sm mt-1">Leads and metrics assigned to you</p>
      </motion.div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <KpiTileSkeleton key={i} />
          ))}
        </div>
      ) : metricsError ? (
        <FetchError
          title="Metrics unavailable"
          message="We couldn't load your dashboard metrics."
          onRetry={loadDashboard}
        />
      ) : (
        <motion.div
          className="grid grid-cols-2 md:grid-cols-5 gap-4"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {cards.map((c) => (
            <motion.div
              key={c.label}
              className="glass-card rounded-lg p-4 border border-white/10 min-w-0"
              whileHover={{ scale: 1.02 }}
            >
              <c.icon className={`w-5 h-5 ${c.color} mb-2`} />
              <p className="text-2xl font-semibold text-white tabular-nums truncate" title={String(c.value)}>{c.value}</p>
              <p className="text-xs text-[#737373] mt-1 truncate">{c.label}</p>
            </motion.div>
          ))}
        </motion.div>
      )}

      <motion.div className="glass-card rounded-lg p-6 border border-white/10">
        <motion.div
          className="flex flex-col sm:flex-row gap-4 mb-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <motion.div className="relative flex-1" whileFocus={{ scale: 1.01 }}>
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#737373]" />
            <Input
              placeholder="Search your leads..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && flushSearch()}
              className="pl-10 bg-black/30 border-white/10 text-white"
            />
          </motion.div>
          <select
            value={tempFilter}
            onChange={(e) => setTempFilter(e.target.value)}
            className="bg-black/30 border border-white/10 rounded-md px-3 py-2 text-sm text-white"
          >
            <option value="all">All temperatures</option>
            <option value="Hot">Hot</option>
            <option value="Warm">Warm</option>
            <option value="Cold">Cold</option>
          </select>
        </motion.div>

        <p className="text-[#737373] text-sm mb-4">
          Showing {leads.length} of {total} assigned leads
          {isLeadsRefetching && <span className="text-[#C5A059] ml-1">(refreshing…)</span>}
        </p>

        {isLeadsInitialLoading ? (
          <LeadGridSkeleton />
        ) : leads.length === 0 ? (
          <p className="text-[#737373] py-8 text-center">No leads assigned yet.</p>
        ) : (
          <div className="relative space-y-2 max-h-[520px] overflow-y-auto">
            {leads.map((lead) => (
              <motion.button
                key={lead.id}
                type="button"
                onClick={() => navigate(`/customer/${lead.id}`)}
                className="w-full flex items-center justify-between p-4 rounded-lg bg-white/[0.02] border border-white/5 hover:border-[#C5A059]/30 text-left transition-colors"
                whileHover={{ x: 4 }}
              >
                <motion.div className="flex-1 min-w-0">
                  <p className="text-white font-medium truncate">{lead.full_name || "Unknown"}</p>
                  <p className="text-[#737373] text-sm truncate">
                    {lead.project || "—"} · {lead.temperature || "—"}
                    {lead.sales_qualification ? ` · ${lead.sales_qualification}` : ""}
                  </p>
                </motion.div>
                <ChevronRight className="w-4 h-4 text-[#C5A059]" />
              </motion.button>
            ))}
            <LoadingOverlay show={isLeadsRefetching} />
          </div>
        )}
      </motion.div>
    </motion.div>
  );
};

export default MyDashboardPage;
