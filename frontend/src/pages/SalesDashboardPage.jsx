import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { useNavigate, useSearchParams } from "react-router-dom";
import { analyticsAPI } from "../lib/api";
import { toast } from "sonner";
import {
  Users,
  Award,
  Clock,
  Flame,
  Snowflake,
  Sun,
  ChevronUp,
  ChevronDown,
  ArrowUpDown,
  Eye,
  MapPin,
  CheckCircle,
  PhoneOff,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { Button } from "../components/ui/button";
import {
  Dialog,
   DialogContent,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { FetchError, LoadingTable } from "../components/loading";

const PERSON_COLORS = ["#C5A059", "#3B82F6", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899", "#14B8A6", "#EF4444"];
const TEMP_COLORS = { Hot: "#EF4444", Warm: "#F59E0B", Cold: "#3B82F6", Dormant: "#6B7280" };
const REP_LEADS_PAGE = 150;

const SalesDashboardPage = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortField, setSortField] = useState("deals_closed");
  const [sortDir, setSortDir] = useState("desc");
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [repLeads, setRepLeads] = useState([]);
  const [repLeadsTotal, setRepLeadsTotal] = useState(0);
  const [repLeadsLoading, setRepLeadsLoading] = useState(false);
  const prefetchedRef = useRef(new Set());
  const listScrollRef = useRef(null);
  const repFetchBusy = useRef(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await analyticsAPI.getSalesDashboard();
      setDashboard(response.data);
    } catch (err) {
      toast.error("Failed to load sales data");
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const salesData = useMemo(() => dashboard?.managers ?? [], [dashboard]);

  const loadRepLeadsPage = useCallback(async (name, skip, { append } = { append: false }) => {
    if (repFetchBusy.current) return;
    repFetchBusy.current = true;
    setRepLeadsLoading(true);
    try {
      const { data } = await analyticsAPI.getSalesRepLeads(name, { skip, limit: REP_LEADS_PAGE });
      setRepLeadsTotal(data.total ?? 0);
      const batch = data.leads || [];
      setRepLeads((prev) => {
        if (!append) return [...batch];
        const seen = new Set(prev.map((l) => l.id));
        const merged = [...prev];
        for (const row of batch) {
          if (!seen.has(row.id)) {
            seen.add(row.id);
            merged.push(row);
          }
        }
        return merged;
      });
    } catch {
      toast.error("Failed to load rep leads");
    } finally {
      setRepLeadsLoading(false);
      repFetchBusy.current = false;
    }
  }, []);

  const prefetchNextRepPage = useCallback(
    (name, nextSkip) => {
      const key = `${name}:${nextSkip}`;
      if (prefetchedRef.current.has(key) || nextSkip >= repLeadsTotal) return;
      prefetchedRef.current.add(key);
      analyticsAPI
        .getSalesRepLeads(name, { skip: nextSkip, limit: REP_LEADS_PAGE })
        .then(({ data }) => {
          const batch = data.leads || [];
          if (!batch.length) return;
          setRepLeads((prev) => {
            const existing = new Set(prev.map((l) => l.id));
            const merged = [...prev];
            for (const row of batch) {
              if (!existing.has(row.id)) merged.push(row);
            }
            return merged;
          });
        })
        .catch(() => {
          prefetchedRef.current.delete(key);
        });
    },
    [repLeadsTotal]
  );

  const openRepModal = useCallback(
    (person) => {
      repFetchBusy.current = false;
      prefetchedRef.current = new Set();
      setSelectedPerson(person);
      setRepLeads([]);
      setRepLeadsTotal(person.total ?? 0);
      loadRepLeadsPage(person.name, 0, { append: false });
    },
    [loadRepLeadsPage]
  );

  const closeRepModal = useCallback(() => {
    setSelectedPerson(null);
    setRepLeads([]);
    setRepLeadsTotal(0);
    prefetchedRef.current = new Set();
    if (searchParams.get("agent")) {
      const next = new URLSearchParams(searchParams);
      next.delete("agent");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (loading || !dashboard?.managers?.length) return;
    const raw = searchParams.get("agent");
    if (!raw) return;
    const decoded = decodeURIComponent(raw).trim();
    if (!decoded) return;
    const match = dashboard.managers.find((m) => m.name.toLowerCase() === decoded.toLowerCase());
    if (match && (!selectedPerson || selectedPerson.name !== match.name)) {
      openRepModal(match);
    }
  }, [loading, dashboard, searchParams, selectedPerson, openRepModal]);

  useEffect(() => {
    if (!selectedPerson?.name) return;
    if (repLeads.length >= REP_LEADS_PAGE && repLeadsTotal > repLeads.length) {
      prefetchNextRepPage(selectedPerson.name, REP_LEADS_PAGE);
    }
  }, [selectedPerson, repLeads.length, repLeadsTotal, prefetchNextRepPage]);

  const performanceCompare = (a, b, dir = sortDir) => {
    const sign = dir === "desc" ? 1 : -1;
    return (
      sign * ((b.deals_closed || 0) - (a.deals_closed || 0)) ||
      sign * ((b.site_visits || 0) - (a.site_visits || 0)) ||
      sign * ((b.total || 0) - (a.total || 0)) ||
      String(a.name || "").localeCompare(String(b.name || ""))
    );
  };

  const sortedData = useMemo(() => {
    return [...salesData]
      .filter((s) => s.name !== "Unassigned")
      .sort((a, b) => {
        if (sortField === "deals_closed" && sortDir === "desc" && a.rank && b.rank) {
          return (a.rank || 0) - (b.rank || 0);
        }
        const av = a[sortField];
        const bv = b[sortField];
        if (typeof av === "number") return sortDir === "desc" ? bv - av : av - bv;
        return sortDir === "desc" ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv));
      });
  }, [salesData, sortField, sortDir]);

  const rankedData = useMemo(() => {
    return [...salesData]
      .filter((s) => s.name !== "Unassigned")
      .sort((a, b) => performanceCompare(a, b, "desc"))
      .slice(0, 10);
  }, [salesData]);

  const teamMeta = dashboard?.team_meta;
  const teamRepCount =
    teamMeta?.canonical_rep_count ??
    teamMeta?.active_rep_count ??
    salesData.filter((s) => s.name !== "Unassigned").length;
  const usersSalesCount = teamMeta?.users_sales_count;

  const totalStats = useMemo(() => dashboard?.totals ?? null, [dashboard]);

  const handleSort = (field) => {
    if (sortField === field) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown size={12} className="text-[#52525B]" />;
    return sortDir === "desc" ? (
      <ChevronDown size={12} className="text-[#C5A059]" />
    ) : (
      <ChevronUp size={12} className="text-[#C5A059]" />
    );
  };

  const comparisonData = useMemo(() => {
    return salesData
      .filter((s) => s.name !== "Unassigned")
      .map((s) => ({
        name: s.name.split(" ")[0],
        Assigned: s.total,
        "Site Visits": s.site_visits,
        Closed: s.deals_closed,
      }));
  }, [salesData]);

  const tempDistribution = useMemo(() => {
    if (!totalStats) return [];
    return [
      { name: "Hot", value: totalStats.hot, color: TEMP_COLORS.Hot },
      { name: "Warm", value: totalStats.warm, color: TEMP_COLORS.Warm },
      { name: "Cold", value: totalStats.cold, color: TEMP_COLORS.Cold },
      { name: "Dormant", value: totalStats.dormant, color: TEMP_COLORS.Dormant },
    ].filter((d) => d.value > 0);
  }, [totalStats]);

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload?.length) {
      return (
        <motion.div className="bg-[#1A1A1A] border border-white/10 rounded-lg p-3 shadow-xl">
          <p className="text-[#C5A059] font-medium mb-1">{label}</p>
          {payload.map((e, i) => (
            <p key={i} className="text-white text-sm">
              {e.name}: {e.value}
            </p>
          ))}
        </motion.div>
      );
    }
    return null;
  };

  const formatDate = (d) => {
    if (!d) return "N/A";
    try {
      return new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    } catch {
      return "N/A";
    }
  };

  const onLeadListScroll = () => {
    const el = listScrollRef.current;
    if (!el || !selectedPerson || repLeadsLoading) return;
    if (repLeads.length >= repLeadsTotal) return;
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 80;
    if (nearBottom) {
      loadRepLeadsPage(selectedPerson.name, repLeads.length, { append: true });
    }
  };

  if (loading && !dashboard) {
    return (
      <motion.div className="space-y-6 max-w-6xl mx-auto p-2">
        <motion.div className="h-10 w-64 rounded bg-white/5 animate-pulse" />
        <motion.div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <motion.div key={i} className="h-20 rounded-lg bg-white/5 animate-pulse" />
          ))}
        </motion.div>
        <motion.div className="h-48 rounded-lg bg-white/5 animate-pulse" />
      </motion.div>
    );
  }

  if (!dashboard) {
    return (
      <motion.div className="space-y-8">
        <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="page-title text-3xl" data-testid="sales-dashboard-title">
            Sales Team Dashboard
          </h1>
        </motion.div>
        <FetchError
          title="Sales dashboard unavailable"
          message="We couldn't load sales team data. Check your connection and try again."
          onRetry={fetchData}
        />
      </motion.div>
    );
  }

  const sortedRepLeads = [...repLeads].sort((a, b) =>
    String(b.updated_at || "").localeCompare(String(a.updated_at || ""))
  );

  return (
    <motion.div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="page-title text-3xl" data-testid="sales-dashboard-title">
          Sales Team Dashboard
        </h1>
        <p className="page-subtitle mt-2">
          Performance analytics and lead distribution across {teamRepCount} presales agents
          {usersSalesCount != null && usersSalesCount !== teamRepCount ? (
            <span className="block text-[#52525B] text-sm mt-1">
              {usersSalesCount} login accounts · {teamRepCount} unique reps on leads (CSV-aligned)
            </span>
          ) : null}
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-8 gap-3"
      >
        {[
          { label: "Total Leads", value: totalStats.total, icon: Users, color: "text-[#C5A059]" },
          { label: "Hot", value: totalStats.hot, icon: Flame, color: "text-red-500" },
          { label: "Warm", value: totalStats.warm, icon: Sun, color: "text-orange-500" },
          { label: "Cold", value: totalStats.cold, icon: Snowflake, color: "text-blue-500" },
          { label: "Dormant", value: totalStats.dormant, icon: Clock, color: "text-gray-500" },
          { label: "RNR", value: totalStats.rnr, icon: PhoneOff, color: "text-yellow-500" },
          { label: "Site Visits", value: totalStats.site_visits, icon: MapPin, color: "text-teal-500" },
          { label: "Deals Closed", value: totalStats.deals_closed, icon: CheckCircle, color: "text-green-500" },
        ].map((s) => (
          <motion.div
            key={s.label}
            className="glass-card rounded-lg p-3 text-center min-w-0"
            data-testid={`stat-${s.label.toLowerCase().replace(/\s/g, "-")}`}
          >
            <s.icon className={`mx-auto ${s.color}`} size={20} />
            <p className="text-[#52525B] text-[10px] uppercase mt-1 truncate">{s.label}</p>
            <p className={`font-serif text-xl tabular-nums truncate ${s.color}`} title={String(s.value)}>
              {s.value}
            </p>
          </motion.div>
        ))}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-card rounded-lg p-6"
      >
        <h3 className="font-serif text-xl text-white mb-4" data-testid="team-overview-title">
          Sales Team Overview
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full" data-testid="sales-team-table">
            <thead>
              <tr className="border-b border-white/10">
                {[
                  { key: "rank", label: "#" },
                  { key: "name", label: "Sales Person" },
                  { key: "total", label: "Total" },
                  { key: "hot", label: "Hot", icon: <Flame size={11} className="text-red-500" /> },
                  { key: "warm", label: "Warm", icon: <Sun size={11} className="text-orange-500" /> },
                  { key: "cold", label: "Cold", icon: <Snowflake size={11} className="text-blue-500" /> },
                  { key: "dormant", label: "Dormant", icon: <Clock size={11} className="text-gray-400" /> },
                  { key: "rnr", label: "RNR", icon: <PhoneOff size={11} className="text-yellow-500" /> },
                  { key: "site_visits", label: "Site Visits" },
                  { key: "deals_closed", label: "Deals Closed" },
                ].map((col) => (
                  <th
                    key={col.key}
                    onClick={() => col.key !== "rank" && handleSort(col.key)}
                    className={`py-3 px-3 text-[#52525B] text-[10px] uppercase tracking-wider ${
                      col.key === "name" ? "text-left" : "text-center"
                    } ${col.key !== "rank" ? "cursor-pointer hover:text-[#C5A059]" : ""}`}
                  >
                    <span className="flex items-center justify-center gap-1">
                      {col.icon} {col.label} {col.key !== "rank" && <SortIcon field={col.key} />}
                    </span>
                  </th>
                ))}
                <th className="py-3 px-3 text-center text-[#52525B] text-[10px] uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedData.map((s, idx) => (
                <tr
                  key={s.name}
                  className={`border-b border-white/5 hover:bg-white/5 transition-colors ${
                    idx === 0 && sortField === "deals_closed" && sortDir === "desc"
                      ? "bg-[#C5A059]/5"
                      : ""
                  }`}
                  data-testid={`sales-row-${s.name}`}
                >
                  <td className="py-3 px-3 text-center">
                    {idx < 3 ? (
                      <Award
                        size={16}
                        className={
                          idx === 0
                            ? "text-[#C5A059] mx-auto"
                            : idx === 1
                              ? "text-gray-400 mx-auto"
                              : "text-orange-700 mx-auto"
                        }
                      />
                    ) : (
                      <span className="text-[#52525B] text-sm">
                        {sortField === "deals_closed" && sortDir === "desc" && s.rank
                          ? s.rank
                          : idx + 1}
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-3">
                    <motion.div className="flex items-center gap-2">
                      <motion.div
                        className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium"
                        style={{
                          backgroundColor: `${PERSON_COLORS[idx % PERSON_COLORS.length]}20`,
                          color: PERSON_COLORS[idx % PERSON_COLORS.length],
                        }}
                      >
                        {s.name.charAt(0)}
                      </motion.div>
                      <span
                        className={`text-sm font-medium ${
                          idx === 0 && sortField === "deals_closed" && sortDir === "desc"
                            ? "text-[#C5A059]"
                            : "text-white"
                        }`}
                      >
                        {s.name}
                      </span>
                    </motion.div>
                  </td>
                  <td className="py-3 px-3 text-center text-white font-medium text-sm">{s.total}</td>
                  <td className="py-3 px-3 text-center text-red-500 text-sm">{s.hot}</td>
                  <td className="py-3 px-3 text-center text-orange-500 text-sm">{s.warm}</td>
                  <td className="py-3 px-3 text-center text-blue-500 text-sm">{s.cold}</td>
                  <td className="py-3 px-3 text-center text-gray-400 text-sm">{s.dormant}</td>
                  <td className="py-3 px-3 text-center text-yellow-500 text-sm">{s.rnr}</td>
                  <td className="py-3 px-3 text-center text-teal-400 text-sm">{s.site_visits}</td>
                  <td className="py-3 px-3 text-center">
                    <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-sm">
                      {s.deals_closed}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-center">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        const next = new URLSearchParams(searchParams);
                        next.set("agent", s.name);
                        setSearchParams(next, { replace: true });
                        openRepModal(s);
                      }}
                      className="text-[#C5A059] hover:bg-[#C5A059]/10 h-7 px-2"
                      data-testid={`view-${s.name}`}
                    >
                      <Eye size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>

      <motion.div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.4 }}
          className="glass-card rounded-lg p-6"
        >
          <h3 className="font-serif text-xl text-white mb-6">Leads Assigned vs Closed</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={comparisonData} margin={{ top: 10, right: 10, left: 0, bottom: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="name" stroke="#A1A1AA" tick={{ fill: "#A1A1AA", fontSize: 11 }} angle={-30} textAnchor="end" />
              <YAxis stroke="#52525B" tick={{ fill: "#A1A1AA", fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ paddingTop: 10 }} />
              <Bar dataKey="Assigned" fill="#C5A059" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Site Visits" fill="#14B8A6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Closed" fill="#10B981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.4 }}
          className="glass-card rounded-lg p-6"
        >
          <h3 className="font-serif text-xl text-white mb-6">Team Lead Temperature Distribution</h3>
          {tempDistribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={tempDistribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {tempDistribution.map((e, i) => (
                    <Cell key={i} fill={e.color} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <motion.div className="bg-[#1A1A1A] border border-white/10 rounded-lg p-3 shadow-xl">
                        <p className="text-[#C5A059] font-medium">{payload[0].name}</p>
                        <p className="text-white">{payload[0].value} leads</p>
                      </motion.div>
                    ) : null
                  }
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-[#52525B] text-sm text-center py-16">
              No temperature distribution data for the current team.
            </p>
          )}
        </motion.div>
      </motion.div>

      <Dialog open={!!selectedPerson} onOpenChange={(open) => !open && closeRepModal()}>
        <DialogContent
          className="bg-[#0F0F0F] border-white/10 text-white max-w-4xl max-h-[90vh] overflow-y-auto"
          data-testid="drilldown-modal"
        >
          {selectedPerson && (
            <>
              <DialogHeader className="mb-2">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-[#C5A059]/20 flex items-center justify-center text-[#C5A059] text-xl font-serif">
                    {selectedPerson.name.charAt(0)}
                  </div>
                  <div className="min-w-0">
                    <DialogTitle className="font-serif text-2xl text-white text-left">
                      {selectedPerson.name}
                    </DialogTitle>
                    <p className="text-[#A1A1AA] text-sm">
                      {selectedPerson.total} leads assigned
                    </p>
                  </div>
                </div>
              </DialogHeader>

              <motion.div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
                {[
                  { label: "Total Assigned", value: selectedPerson.total, color: "text-[#C5A059]", bg: "bg-[#C5A059]/10" },
                  { label: "Contacted", value: selectedPerson.contacted ?? 0, color: "text-blue-400", bg: "bg-blue-500/10" },
                  { label: "Site Visit", value: selectedPerson.site_visits, color: "text-teal-400", bg: "bg-teal-500/10" },
                  { label: "Negotiation", value: selectedPerson.negotiation ?? 0, color: "text-purple-400", bg: "bg-purple-500/10" },
                  { label: "Closed", value: selectedPerson.deals_closed, color: "text-green-400", bg: "bg-green-500/10" },
                ].map((f, i) => (
                  <motion.div key={f.label} className={`p-3 rounded-lg ${f.bg} text-center relative`}>
                    <p className="text-[#52525B] text-[10px] uppercase">{f.label}</p>
                    <p className={`font-serif text-2xl ${f.color}`}>{f.value}</p>
                    {i < 4 && (
                      <motion.div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 text-[#52525B] z-10">
                        &#8594;
                      </motion.div>
                    )}
                  </motion.div>
                ))}
              </motion.div>

              <h3 className="font-serif text-lg text-white mb-3">All Assigned Leads</h3>
              <p className="text-[#52525B] text-xs mb-2">
                Showing {repLeads.length} of {repLeadsTotal}
                {repLeadsLoading ? " · Loading…" : ""}
              </p>
              <motion.div
                ref={listScrollRef}
                onScroll={onLeadListScroll}
                className="max-h-80 overflow-y-auto space-y-2 pr-2"
              >
                {repLeadsLoading && repLeads.length === 0 ? (
                  <LoadingTable rows={5} />
                ) : null}
                {sortedRepLeads.map((lead) => {
                  const displayName =
                    lead.full_name ||
                    `${lead.first_name || ""} ${lead.last_name || ""}`.trim() ||
                    "Unknown";
                  return (
                    <motion.div
                      key={lead.id}
                      onClick={() => {
                        closeRepModal();
                        navigate(`/customer/${lead.id}`);
                      }}
                      className="flex items-center gap-3 p-3 rounded-lg bg-black/30 border border-white/5 hover:border-[#C5A059]/30 cursor-pointer transition-all group"
                      data-testid={`drilldown-lead-${lead.id}`}
                    >
                      <motion.div className="w-9 h-9 rounded-full bg-[#C5A059]/20 flex items-center justify-center text-[#C5A059] text-sm flex-shrink-0">
                        {displayName.charAt(0)}
                      </motion.div>
                      <motion.div className="flex-1 min-w-0">
                        <p className="text-white text-sm font-medium truncate group-hover:text-[#C5A059] transition-colors">
                          {displayName}
                        </p>
                        <p className="text-[#52525B] text-xs truncate">{lead.project || "No project"}</p>
                      </motion.div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                          lead.temperature === "Hot"
                            ? "bg-red-500/20 text-red-400"
                            : lead.temperature === "Warm"
                              ? "bg-orange-500/20 text-orange-400"
                              : "bg-blue-500/20 text-blue-400"
                        }`}
                      >
                        {lead.temperature}
                      </span>
                      <span className="text-[#52525B] text-xs">{lead.lead_status}</span>
                      <span className="text-[#52525B] text-[10px]">
                        {formatDate(lead.updated_at || lead.created_at)}
                      </span>
                    </motion.div>
                  );
                })}
              </motion.div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </motion.div>
  );
};

export default SalesDashboardPage;
