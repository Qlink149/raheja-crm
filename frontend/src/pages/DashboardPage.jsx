import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Users,
  Crown,
  Flame,
  TrendingUp,
  Home,
  UserCircle,
  Settings,
  LogOut,
  Building2,
  MapPin,
  Snowflake,
  Clock,
  Calendar,
  Filter,
  ChevronDown,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";

const DashboardPage = ({ onLogout, currentUser }) => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeFilter, setTimeFilter] = useState("all");
  const [greeting, setGreeting] = useState("");
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState("all");
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [customStartDate, setCustomStartDate] = useState("");
  const [customEndDate, setCustomEndDate] = useState("");

  useEffect(() => {
    const hour = new Date().getHours();
    if (hour < 12) setGreeting("Good Morning");
    else if (hour < 17) setGreeting("Good Afternoon");
    else setGreeting("Good Evening");
  }, []);

  useEffect(() => {
    fetchStats();
    fetchProjects();
  }, [timeFilter, selectedProject, customStartDate, customEndDate]);

  const fetchProjects = async () => {
    try {
      const response = await api.get("/projects");
      setProjects(response.data);
    } catch (error) {
      console.error("Error fetching projects:", error);
    }
  };

  const fetchStats = async () => {
    try {
      const params = {};
      if (selectedProject && selectedProject !== "all") {
        params.project = selectedProject;
      }
      // Convert timeFilter to days
      if (timeFilter === "7days") params.days = 7;
      else if (timeFilter === "15days") params.days = 15;
      else if (timeFilter === "30days") params.days = 30;
      else if (timeFilter === "custom") {
        if (customStartDate) params.start_date = customStartDate;
        if (customEndDate)   params.end_date   = customEndDate;
      }
      // "alltime" = no days filter

      const response = await api.get("/dashboard/stats", { params });
      setStats(response.data);
    } catch (error) {
      console.error("Error fetching stats:", error);
    } finally {
      setLoading(false);
    }
  };

  const formatNumber = (num) => {
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num?.toString() || "0";
  };

  const timeFilters = ["7 Days", "15 Days", "30 Days", "All Time"];

  // Prepare chart data
  const sourceChartData = stats?.lead_source_stats
    ? Object.entries(stats.lead_source_stats)
        .slice(0, 6)
        .map(([name, value]) => ({ name, value }))
    : [];

  const statusChartData = stats?.lead_status_stats
    ? Object.entries(stats.lead_status_stats).map(([name, value]) => ({
        name,
        value,
      }))
    : [];

  // Regional Demand Heatmap removed — location data no longer rendered.

  const COLORS = ["#C5A059", "#8A6D3B", "#E5C585", "#6B5C3E", "#D4B96A"];
  const STATUS_COLORS = {
    Qualified: "#10B981",
    Open: "#C5A059",
    Lost: "#7F1D1D",
  };

  const containerVariants = {
    hidden: { opacity: 1 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.05 },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 10 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  };

  return (
    <div className="flex min-h-screen bg-[#0A0A0A]">
      <Sidebar activePage="dashboard" onLogout={onLogout} currentUser={currentUser} />

      {/* Main Content */}
      <main className="flex-1 p-8 ml-20 lg:ml-64">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="max-w-7xl mx-auto"
        >
          {/* Header */}
          <motion.div variants={itemVariants} className="mb-6">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              <div>
                <h1 data-testid="dashboard-greeting" className="font-serif text-3xl lg:text-4xl text-white tracking-tight">
                  {greeting},{" "}
                  <span className="text-[#C5A059] animate-pulse-gold">
                    {currentUser?.name || "Ravinder"}
                  </span>
                </h1>
                <p className="text-[#A3A3A3] mt-2">
                  Your sales intelligence command center
                </p>
              </div>

              {/* Filters Row */}
              <div className="flex flex-wrap items-center gap-3">
                {/* Project Filter */}
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="bg-[#1A1A1A] border-white/10 text-white hover:bg-white/5 hover:text-[#C5A059]">
                      <Building2 className="w-4 h-4 mr-2" />
                      {selectedProject === "all" ? "All Projects" : selectedProject.replace("Rustomjee ", "")}
                      <ChevronDown className="w-4 h-4 ml-2" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-64 bg-[#1A1A1A] border-white/10 p-2">
                    <div className="max-h-64 overflow-y-auto space-y-1">
                      <button
                        onClick={() => setSelectedProject("all")}
                        className={`w-full text-left px-3 py-2 text-sm rounded ${
                          selectedProject === "all" ? "bg-[#C5A059] text-black" : "text-white hover:bg-white/10"
                        }`}
                      >
                        All Projects
                      </button>
                      {projects.map((proj) => (
                        <button
                          key={proj.name}
                          onClick={() => setSelectedProject(proj.name)}
                          className={`w-full text-left px-3 py-2 text-sm rounded truncate ${
                            selectedProject === proj.name ? "bg-[#C5A059] text-black" : "text-white hover:bg-white/10"
                          }`}
                        >
                          {proj.name} ({proj.count})
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>

                {/* Time Filter */}
                <div className="flex items-center gap-1 bg-[#1A1A1A] rounded-lg p-1 border border-white/10">
                  {timeFilters.map((filter) => (
                    <button
                      key={filter}
                      data-testid={`time-filter-${filter.toLowerCase().replace(" ", "-")}`}
                      onClick={() => {
                        setTimeFilter(filter.toLowerCase().replace(" ", ""));
                        setShowDatePicker(false);
                      }}
                      className={`px-3 py-2 text-xs rounded-md transition-all duration-300 ${
                        timeFilter === filter.toLowerCase().replace(" ", "")
                          ? "bg-[#C5A059] text-black font-semibold"
                          : "text-[#A3A3A3] hover:text-white"
                      }`}
                    >
                      {filter}
                    </button>
                  ))}
                  {/* Custom Date */}
                  <Popover open={showDatePicker} onOpenChange={setShowDatePicker}>
                    <PopoverTrigger asChild>
                      <button
                        className={`px-3 py-2 text-xs rounded-md transition-all duration-300 ${
                          timeFilter === "custom"
                            ? "bg-[#C5A059] text-black font-semibold"
                            : "text-[#A3A3A3] hover:text-white"
                        }`}
                      >
                        <Calendar className="w-4 h-4" />
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className="w-72 bg-[#1A1A1A] border-white/10 p-4">
                      <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-3">Custom Date Range</p>
                      <div className="space-y-3">
                        <div>
                          <label className="text-xs text-[#A3A3A3]">Start Date</label>
                          <Input
                            type="date"
                            value={customStartDate}
                            onChange={(e) => setCustomStartDate(e.target.value)}
                            className="bg-black/20 border-white/10 text-white"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-[#A3A3A3]">End Date</label>
                          <Input
                            type="date"
                            value={customEndDate}
                            onChange={(e) => setCustomEndDate(e.target.value)}
                            className="bg-black/20 border-white/10 text-white"
                          />
                        </div>
                        <Button
                          onClick={() => {
                            setTimeFilter("custom");
                            setShowDatePicker(false);
                          }}
                          className="w-full bg-[#C5A059] text-black hover:bg-[#E5C585]"
                        >
                          Apply Range
                        </Button>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
              </div>
            </div>
          </motion.div>

          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-8 h-8 border-2 border-[#C5A059] border-t-transparent rounded-full spinner" />
            </div>
          ) : !stats ? (
            <div className="flex items-center justify-center h-64">
              <p className="text-[#A3A3A3]">Failed to load data. Please refresh.</p>
            </div>
          ) : (
            <>
              {/* Prominent Cold & Dormant Leads Section */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6"
              >
                {/* Cold Leads Alert */}
                <motion.div
                  className="glass-card rounded-lg p-5 cursor-pointer border-l-4 border-l-blue-500"
                  whileHover={{ scale: 1.01, borderColor: "rgba(59, 130, 246, 0.5)" }}
                  onClick={() => navigate("/virtual-customer?temperature=Cold")}
                  data-testid="metric-cold-leads"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="p-3 bg-blue-900/30 rounded-lg">
                        <Snowflake className="w-6 h-6 text-blue-400" strokeWidth={1.5} />
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-widest text-blue-400 font-semibold">
                          Cold Leads
                        </p>
                        <p className="font-serif text-3xl text-white">
                          {formatNumber(stats?.cold_leads)}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-xs text-[#A3A3A3]">Needs Re-engagement</span>
                      <p className="text-sm text-blue-400 font-semibold">Action Required</p>
                    </div>
                  </div>
                </motion.div>

                {/* Dormant Leads Alert */}
                <motion.div
                  className="glass-card rounded-lg p-5 cursor-pointer border-l-4 border-l-amber-500"
                  whileHover={{ scale: 1.01, borderColor: "rgba(245, 158, 11, 0.5)" }}
                  onClick={() => navigate("/virtual-customer?temperature=Cold")}
                  data-testid="metric-dormant-leads"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="p-3 bg-amber-900/30 rounded-lg">
                        <Clock className="w-6 h-6 text-amber-400" strokeWidth={1.5} />
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-widest text-amber-400 font-semibold">
                          Dormant Leads
                        </p>
                        <p className="font-serif text-3xl text-white">
                          {formatNumber(stats?.dormant_leads)}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-xs text-[#A3A3A3]">Lost / Inactive</span>
                      <p className="text-sm text-amber-400 font-semibold">Revive Campaign</p>
                    </div>
                  </div>
                </motion.div>
              </motion.div>

              {/* Metric Tiles */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
              >
                {/* Total Leads */}
                <motion.div
                  className="glass-card rounded-lg p-6 cursor-pointer"
                  whileHover={{ scale: 1.02, borderColor: "rgba(197, 160, 89, 0.5)" }}
                  onClick={() => navigate("/virtual-customer")}
                  data-testid="metric-total-leads"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="p-3 bg-[#C5A059]/10 rounded-lg">
                      <Users className="w-6 h-6 text-[#C5A059]" strokeWidth={1.5} />
                    </div>
                    <span className="px-2 py-1 text-xs bg-[#C5A059]/20 text-[#C5A059] rounded border border-[#C5A059]/30">
                      Live
                    </span>
                  </div>
                  <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-1">
                    Total Leads
                  </p>
                  <p className="font-serif text-4xl text-white">
                    {formatNumber(stats?.total_leads)}
                  </p>
                </motion.div>

                {/* VIP Pipeline */}
                <motion.div
                  className="glass-card rounded-lg p-6 cursor-pointer"
                  whileHover={{ scale: 1.02, borderColor: "rgba(197, 160, 89, 0.5)" }}
                  onClick={() => navigate("/virtual-customer?vip=true")}
                  data-testid="metric-vip-pipeline"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="p-3 bg-[#C5A059]/10 rounded-lg">
                      <Crown className="w-6 h-6 text-[#C5A059]" strokeWidth={1.5} />
                    </div>
                    <span className="px-2 py-1 text-xs bg-[#C5A059]/20 text-[#C5A059] rounded border border-[#C5A059]/30">
                      VIP
                    </span>
                  </div>
                  <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-1">
                    VIP Pipeline
                  </p>
                  <p className="font-serif text-4xl text-white">
                    {formatNumber(stats?.vip_pipeline)}
                  </p>
                </motion.div>

                {/* Hot Leads */}
                <motion.div
                  className="glass-card rounded-lg p-6 cursor-pointer"
                  whileHover={{ scale: 1.02, borderColor: "rgba(197, 160, 89, 0.5)" }}
                  onClick={() => navigate("/virtual-customer?temperature=Hot")}
                  data-testid="metric-hot-leads"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="p-3 bg-red-900/20 rounded-lg">
                      <Flame className="w-6 h-6 text-red-400" strokeWidth={1.5} />
                    </div>
                    <span className="badge-hot px-2 py-1 text-xs rounded">
                      Active
                    </span>
                  </div>
                  <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-1">
                    Hot Leads
                  </p>
                  <p className="font-serif text-4xl text-white">
                    {formatNumber(stats?.hot_leads)}
                  </p>
                </motion.div>

                {/* Qualified */}
                <motion.div
                  className="glass-card rounded-lg p-6 cursor-pointer"
                  whileHover={{ scale: 1.02, borderColor: "rgba(197, 160, 89, 0.5)" }}
                  data-testid="metric-qualified"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="p-3 bg-emerald-900/20 rounded-lg">
                      <TrendingUp className="w-6 h-6 text-emerald-400" strokeWidth={1.5} />
                    </div>
                    <span className="px-2 py-1 text-xs bg-emerald-900/30 text-emerald-300 rounded border border-emerald-800/50">
                      Qualified
                    </span>
                  </div>
                  <p className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-1">
                    Qualified Leads
                  </p>
                  <p className="font-serif text-4xl text-white">
                    {formatNumber(stats?.qualified_leads)}
                  </p>
                </motion.div>
              </motion.div>

              {/* Charts Section */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Lead Source Performance */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.1 }}
                  className="lg:col-span-8 glass-card rounded-lg p-6"
                >
                  <h3 className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-6">
                    Lead Source Performance
                  </h3>
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={sourceChartData}
                        layout="vertical"
                        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                      >
                        <XAxis
                          type="number"
                          tick={{ fill: "#A3A3A3", fontSize: 12 }}
                          axisLine={{ stroke: "#333" }}
                          tickLine={false}
                        />
                        <YAxis
                          type="category"
                          dataKey="name"
                          tick={{ fill: "#A3A3A3", fontSize: 12 }}
                          axisLine={false}
                          tickLine={false}
                          width={80}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#1A1A1A",
                            border: "1px solid rgba(197, 160, 89, 0.3)",
                            borderRadius: "8px",
                            color: "#fff",
                          }}
                        />
                        <Bar
                          dataKey="value"
                          fill="#C5A059"
                          radius={[0, 4, 4, 0]}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </motion.div>

                {/* Lead Status Distribution */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.2 }}
                  className="lg:col-span-4 glass-card rounded-lg p-6"
                >
                  <h3 className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-6">
                    Lead Status Distribution
                  </h3>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={statusChartData}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={90}
                          paddingAngle={2}
                          dataKey="value"
                        >
                          {statusChartData.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={STATUS_COLORS[entry.name] || COLORS[index]}
                            />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#1A1A1A",
                            border: "1px solid rgba(197, 160, 89, 0.3)",
                            borderRadius: "8px",
                            color: "#fff",
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  {/* Legend */}
                  <div className="flex flex-wrap justify-center gap-4 mt-4">
                    {statusChartData.map((entry, index) => (
                      <div key={entry.name} className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{
                            backgroundColor:
                              STATUS_COLORS[entry.name] || COLORS[index],
                          }}
                        />
                        <span className="text-sm text-[#A3A3A3]">
                          {entry.name}: {formatNumber(entry.value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </motion.div>

                {/* Regional Demand Heatmap removed */}
              </div>
            </>
          )}
        </motion.div>
      </main>
    </div>
  );
};

export default DashboardPage;
