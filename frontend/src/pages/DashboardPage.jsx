import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import {
  mapLeadSources,
  mapStatusBreakdown,
  mapDispositionBreakdown,
  parseProjectsPayload,
  buildStatsParams,
  formatDashboardNumber,
  REGIONAL_COLORS,
} from "../lib/adapters/dashboardAdapter";
import ChartTooltip from "../components/shared/ChartTooltip";
import {
  Users,
  Crown,
  Flame,
  CheckCircle,
  Snowflake,
  TrendingDown,
  Calendar,
  ChevronDown,
  Info,
  Building,
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
} from "recharts";
import { Button } from "../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { Calendar as CalendarUI } from "../components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import {
  Tooltip as TooltipUI,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../components/ui/tooltip";

const LEAD_CRITERIA = {
  cold: {
    title: "Cold Lead Criteria",
    rules: [
      "No response to calls for 7+ days",
      "Lead status marked as 'Lost' or 'Not Interested'",
      "No engagement with marketing materials",
      "Budget mismatch with available projects",
    ],
  },
  dormant: {
    title: "Dormant Lead Criteria",
    rules: [
      "No activity or updates in 7+ days",
      "Last contact attempt was unsuccessful",
      "No site visit scheduled",
      "Pending follow-up overdue by 5+ days",
    ],
  },
  hot: {
    title: "Hot Lead Criteria",
    rules: [
      "Recent positive engagement (last 3 days)",
      "Site visit completed or scheduled",
      "Budget aligned with project pricing",
      "Expressed strong purchase intent",
      "Responded positively to follow-ups",
    ],
  },
};

const DashboardPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [projectList, setProjectList] = useState([]);
  const [projectMeta, setProjectMeta] = useState(null);
  const [salesOwners, setSalesOwners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [timeFilter, setTimeFilter] = useState("all");
  const [projectFilter, setProjectFilter] = useState("all");
  const [dateRange, setDateRange] = useState(null);

  const timeFilters = [
    { value: "7", label: "7 Days" },
    { value: "15", label: "15 Days" },
    { value: "30", label: "30 Days" },
    { value: "all", label: "All Time" },
    { value: "custom", label: "Custom Range" },
  ];

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = buildStatsParams(timeFilter, projectFilter, dateRange);
      const [statsRes, projectsRes, ownersRes] = await Promise.all([
        api.get("/dashboard/stats", { params }),
        api.get("/dashboard/projects"),
        api.get("/dashboard/sales-owners", { params }).catch(() => ({ data: [] })),
      ]);
      setStats(statsRes.data);
      const { projects, meta } = parseProjectsPayload(projectsRes.data);
      setProjectList(projects);
      setProjectMeta(meta);
      setSalesOwners(ownersRes.data || []);
    } catch (error) {
      console.error("Failed to fetch dashboard:", error);
    } finally {
      setLoading(false);
    }
  }, [timeFilter, projectFilter, dateRange]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleProjectClick = (projectName) => {
    if (projectName === "__none__") {
      navigate("/virtual-customer?project=__none__&futwork_sync_status=all");
      return;
    }
    navigate(
      `/virtual-customer?project=${encodeURIComponent(projectName)}&futwork_sync_status=all`
    );
  };

  const leadSources = mapLeadSources(stats);
  const statusData = mapStatusBreakdown(stats);
  const dispositionData = mapDispositionBreakdown(stats);
  const projectsForGrid = projectList;
  const otherProjectCard =
    projectMeta && projectMeta.otherCount > 0
      ? { name: "__none__", label: "Other / No project", count: projectMeta.otherCount }
      : null;
  const displayProjects = otherProjectCard
    ? [...projectsForGrid, { name: otherProjectCard.name, count: otherProjectCard.count, label: otherProjectCard.label }]
    : projectsForGrid;

  const handleDispositionClick = (entry) => {
    if (!entry?.name) return;
    navigate(`/virtual-customer?disposition=${encodeURIComponent(entry.name)}`);
  };
  const projectNames = projectsForGrid.map((p) => p.name);

  const LeadCriteriaTooltip = ({ type }) => {
    const criteria = LEAD_CRITERIA[type];
    if (!criteria) return null;
    return (
      <TooltipProvider>
        <TooltipUI>
          <TooltipTrigger asChild>
            <button type="button" className="ml-2 text-[#52525B] hover:text-[#C5A059] transition-colors">
              <Info size={16} />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" className="bg-[#1A1A1A] border-white/10 p-4 max-w-xs">
            <p className="text-[#C5A059] font-medium mb-2">{criteria.title}</p>
            <ul className="space-y-1">
              {criteria.rules.map((rule, idx) => (
                <li key={idx} className="text-[#A1A1AA] text-xs flex items-start gap-2">
                  <span className="text-[#C5A059] mt-0.5">•</span>
                  {rule}
                </li>
              ))}
            </ul>
          </TooltipContent>
        </TooltipUI>
      </TooltipProvider>
    );
  };

  if (loading) {
    return (
      <motion.div className="flex items-center justify-center h-64">
        <p className="text-[#C5A059] animate-pulse">Loading dashboard...</p>
      </motion.div>
    );
  }

  return (
    <motion.div className="space-y-8">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="relative rounded-xl overflow-hidden h-40 md:h-48"
        data-testid="hero-banner"
      >
        <img
          src="https://images.unsplash.com/photo-1758448511648-d7d8e1993c3f?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85&w=1920&h=400&fit=crop"
          alt="Luxury property"
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/60 to-black/30" />
        <div className="relative z-10 h-full flex items-center px-8">
          <div>
            <p className="text-[#C5A059] text-sm font-medium tracking-widest uppercase">Rustomjee</p>
            <h1 className="font-serif text-3xl lg:text-4xl text-white mt-1" data-testid="dashboard-greeting">
              Hello, {user?.full_name?.split(" ")[0] || user?.email?.split("@")[0] || "there"}
            </h1>
            <p className="text-white/70 mt-1 text-sm">
              Your sales intelligence overview — premium residences across Mumbai
            </p>
          </div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex flex-wrap items-center gap-3"
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              className="bg-[#1A1A1A] border-white/10 text-white hover:bg-white/5 hover:text-[#C5A059]"
              data-testid="time-filter-dropdown"
            >
              <Calendar size={16} className="mr-2" />
              {timeFilters.find((f) => f.value === timeFilter)?.label || "All Time"}
              <ChevronDown size={16} className="ml-2" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="bg-[#1A1A1A] border-white/10">
            {timeFilters.map((filter) => (
              <DropdownMenuItem
                key={filter.value}
                onClick={() => setTimeFilter(filter.value)}
                className="text-white hover:bg-[#C5A059]/10 hover:text-[#C5A059] cursor-pointer"
              >
                {filter.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              className="bg-[#1A1A1A] border-white/10 text-white hover:bg-white/5 hover:text-[#C5A059]"
              data-testid="project-filter-dropdown"
            >
              {projectFilter === "all" ? "All Projects" : projectFilter}
              <ChevronDown size={16} className="ml-2" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="bg-[#1A1A1A] border-white/10">
            <DropdownMenuItem
              onClick={() => setProjectFilter("all")}
              className="text-white hover:bg-[#C5A059]/10 hover:text-[#C5A059] cursor-pointer"
            >
              All Projects
            </DropdownMenuItem>
            {projectNames.map((project) => (
              <DropdownMenuItem
                key={project}
                onClick={() => setProjectFilter(project)}
                className="text-white hover:bg-[#C5A059]/10 hover:text-[#C5A059] cursor-pointer"
              >
                {project}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {timeFilter === "custom" && (
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="bg-[#1A1A1A] border-white/10 text-white hover:bg-white/5">
                Select Date Range
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0 bg-[#1A1A1A] border-white/10">
              <CalendarUI
                mode="range"
                selected={dateRange}
                onSelect={setDateRange}
                className="bg-[#1A1A1A] text-white"
              />
            </PopoverContent>
          </Popover>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-1 md:grid-cols-2 gap-4"
      >
        <div className="glass-card rounded-lg p-6 border-l-4 border-blue-500 card-hover" data-testid="cold-leads-tile">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center">
                <p className="text-[#A1A1AA] text-sm uppercase tracking-wider">Cold Leads</p>
                <LeadCriteriaTooltip type="cold" />
              </div>
              <p className="font-serif text-4xl text-white mt-2">{stats?.cold_leads ?? 0}</p>
              <p className="text-blue-400 text-sm mt-1">Needs Re-engagement</p>
            </div>
            <div className="w-14 h-14 rounded-full bg-blue-500/20 flex items-center justify-center">
              <Snowflake className="text-blue-500" size={28} />
            </div>
          </div>
        </div>

        <div className="glass-card rounded-lg p-6 border-l-4 border-orange-500 card-hover" data-testid="dormant-leads-tile">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center">
                <p className="text-[#A1A1AA] text-sm uppercase tracking-wider">Dormant Leads</p>
                <LeadCriteriaTooltip type="dormant" />
              </div>
              <p className="font-serif text-4xl text-white mt-2">{stats?.dormant_leads ?? 0}</p>
              <p className="text-orange-400 text-sm mt-1">No activity in 7+ days</p>
            </div>
            <div className="w-14 h-14 rounded-full bg-orange-500/20 flex items-center justify-center">
              <TrendingDown className="text-orange-500" size={28} />
            </div>
          </div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <div className="glass-card rounded-lg p-6 card-hover" data-testid="total-leads-tile">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 rounded-lg bg-[#C5A059]/20 flex items-center justify-center">
              <Users className="text-[#C5A059]" size={24} />
            </div>
          </div>
          <p className="text-[#A1A1AA] text-sm">Total Leads</p>
          <p className="font-serif text-3xl text-white mt-1">{stats?.total_leads ?? 0}</p>
        </div>

        <div className="glass-card rounded-lg p-6 card-hover" data-testid="vip-leads-tile">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 rounded-lg bg-purple-500/20 flex items-center justify-center">
              <Crown className="text-purple-500" size={24} />
            </div>
          </div>
          <p className="text-[#A1A1AA] text-sm">VIP Pipeline</p>
          <p className="font-serif text-3xl text-white mt-1">{stats?.vip_pipeline ?? 0}</p>
        </div>

        <div className="glass-card rounded-lg p-6 card-hover" data-testid="hot-leads-tile">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 rounded-lg bg-red-500/20 flex items-center justify-center">
              <Flame className="text-red-500" size={24} />
            </div>
            <LeadCriteriaTooltip type="hot" />
          </div>
          <p className="text-[#A1A1AA] text-sm">Hot Leads</p>
          <p className="font-serif text-3xl text-white mt-1">{stats?.hot_leads ?? 0}</p>
        </div>

        <div className="glass-card rounded-lg p-6 card-hover" data-testid="qualified-leads-tile">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 rounded-lg bg-green-500/20 flex items-center justify-center">
              <CheckCircle className="text-green-500" size={24} />
            </div>
          </div>
          <p className="text-[#A1A1AA] text-sm">Qualified Leads</p>
          <p className="font-serif text-3xl text-white mt-1">{stats?.qualified_leads ?? 0}</p>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="glass-card rounded-lg p-6"
          data-testid="lead-source-chart"
        >
          <h3 className="font-serif text-xl text-white mb-6">Lead Source Performance</h3>
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={leadSources} layout="vertical" margin={{ top: 0, right: 20, bottom: 0, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis type="number" stroke="#52525B" />
              <YAxis
                type="category"
                dataKey="name"
                stroke="#A1A1AA"
                tick={{ fill: "#A1A1AA", fontSize: 11 }}
                width={140}
              />
              <Tooltip content={<ChartTooltip />} />
              <defs>
                <linearGradient id="goldGradient" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#C5A059" />
                  <stop offset="100%" stopColor="#E5C079" />
                </linearGradient>
              </defs>
              <Bar dataKey="count" fill="url(#goldGradient)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="glass-card rounded-lg p-6"
          data-testid="lead-status-chart"
        >
          <h3 className="font-serif text-xl text-white mb-6">Lead Status Distribution</h3>
          <div className="flex items-center justify-center">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={5}
                  dataKey="value"
                  nameKey="name"
                >
                  {statusData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload?.length) {
                      return (
                        <div className="bg-[#1A1A1A] border border-white/10 rounded-lg p-3 shadow-xl">
                          <p className="text-[#C5A059] font-medium">{payload[0].name}</p>
                          <p className="text-white">{payload[0].value} leads</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap justify-center gap-x-4 gap-y-2 mt-4">
            {statusData.map((item) => (
              <div key={item.name} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
                <span className="text-[#A1A1AA] text-xs whitespace-nowrap">
                  {item.name} ({item.value})
                </span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {dispositionData.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="glass-card rounded-lg p-6"
          data-testid="disposition-chart"
        >
          <h3 className="font-serif text-xl text-white mb-2">Disposition Distribution</h3>
          <p className="text-[#737373] text-xs mb-4">Click a slice to filter Virtual Customer</p>
          <div className="flex items-center justify-center">
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={dispositionData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={95}
                  paddingAngle={4}
                  dataKey="value"
                  nameKey="name"
                  style={{ cursor: "pointer" }}
                  onClick={(_, index) => handleDispositionClick(dispositionData[index])}
                >
                  {dispositionData.map((entry, index) => (
                    <Cell key={`disp-cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload?.length) {
                      return (
                        <div className="bg-[#1A1A1A] border border-white/10 rounded-lg p-3 shadow-xl">
                          <p className="text-[#C5A059] font-medium">{payload[0].name}</p>
                          <p className="text-white">{payload[0].value} leads</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="glass-card rounded-lg p-6"
        data-testid="sales-team-heatmap"
      >
        <h3 className="font-serif text-xl text-white mb-1">Top 10 Sales Agents</h3>
        <p className="text-[#52525B] text-sm mb-6">
          By assigned presales leads
          {salesOwners.length > 0
            ? ` · ${formatDashboardNumber(salesOwners.reduce((s, o) => s + (o.count || 0), 0))} leads shown`
            : ""}
        </p>
        {salesOwners.length === 0 ? (
          <p className="text-[#52525B] text-sm">No assigned agent data for the selected filters.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            {salesOwners.map((owner, index) => {
              const colorScheme = REGIONAL_COLORS[index % REGIONAL_COLORS.length];
              return (
                <div
                  key={owner.name}
                  role="button"
                  tabIndex={0}
                  className="p-4 rounded-lg text-center transition-all hover:scale-105 cursor-pointer"
                  onClick={() =>
                    navigate(
                      `/virtual-customer?assigned_rep=${encodeURIComponent(owner.name)}&futwork_sync_status=all`
                    )
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      navigate(
                        `/virtual-customer?assigned_rep=${encodeURIComponent(owner.name)}&futwork_sync_status=all`
                      );
                    }
                  }}
                  style={{
                    background: colorScheme.bg,
                    border: `2px solid ${colorScheme.border}`,
                  }}
                >
                  <p className="text-white font-medium text-sm truncate">{owner.name}</p>
                  <p className="font-serif text-2xl mt-1" style={{ color: colorScheme.text }}>
                    {owner.count}
                  </p>
                  <p className="text-[#52525B] text-xs">leads</p>
                </div>
              );
            })}
          </div>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="glass-card rounded-lg p-6"
        data-testid="project-distribution"
      >
        <h3 className="font-serif text-xl text-white mb-2">Project Interest Distribution</h3>
        <p className="text-[#52525B] text-sm mb-4">
          Click on a project to view its leads
          {projectMeta ? (
            <>
              {" "}
              · Top 10 shown · {formatDashboardNumber(projectMeta.withProject)} with project ·{" "}
              {formatDashboardNumber(projectMeta.withoutProject)} without ·{" "}
              {formatDashboardNumber(projectMeta.totalLeads)} total
            </>
          ) : null}
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {displayProjects.map((project) => (
            <div
              key={project.name}
              role="button"
              tabIndex={0}
              onClick={() => handleProjectClick(project.name)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleProjectClick(project.name);
              }}
              className="p-4 rounded-lg bg-[#1A1A1A] border border-white/10 hover:border-[#C5A059]/50 transition-all cursor-pointer group overflow-hidden relative"
              data-testid={`project-card-${project.name}`}
            >
              <div className="relative z-10">
                <div className="flex items-center gap-2 mb-3">
                  <Building className="text-[#C5A059]" size={18} />
                  <span className="text-white font-medium group-hover:text-[#C5A059] transition-colors">
                    {project.label || project.name}
                  </span>
                </div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[#52525B] text-sm">Leads</span>
                  <span className="text-[#C5A059] font-serif text-xl">{project.count}</span>
                </div>
                <div className="h-2 bg-black/50 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-[#C5A059] to-[#E5C079] rounded-full transition-all duration-500"
                    style={{
                      width: `${(project.count / Math.max(...displayProjects.map((p) => p.count), 1)) * 100}%`,
                    }}
                  />
                </div>
                <p className="text-[#52525B] text-xs mt-2 group-hover:text-[#A1A1AA] transition-colors">
                  Click to view leads →
                </p>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
};

export default DashboardPage;
