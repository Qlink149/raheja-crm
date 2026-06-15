export const REGIONAL_COLORS = [
  { bg: "rgba(59, 130, 246, 0.2)", border: "rgba(59, 130, 246, 0.5)", text: "#3B82F6" },
  { bg: "rgba(16, 185, 129, 0.2)", border: "rgba(16, 185, 129, 0.5)", text: "#10B981" },
  { bg: "rgba(245, 158, 11, 0.2)", border: "rgba(245, 158, 11, 0.5)", text: "#F59E0B" },
  { bg: "rgba(239, 68, 68, 0.2)", border: "rgba(239, 68, 68, 0.5)", text: "#EF4444" },
  { bg: "rgba(168, 85, 247, 0.2)", border: "rgba(168, 85, 247, 0.5)", text: "#A855F7" },
  { bg: "rgba(236, 72, 153, 0.2)", border: "rgba(236, 72, 153, 0.5)", text: "#EC4899" },
  { bg: "rgba(20, 184, 166, 0.2)", border: "rgba(20, 184, 166, 0.5)", text: "#14B8A6" },
  { bg: "rgba(99, 102, 241, 0.2)", border: "rgba(99, 102, 241, 0.5)", text: "#6366F1" },
];

const CHART_COLORS = [
  "#059669",
  "#D97706",
  "#DC2626",
  "#3B82F6",
  "#8B5CF6",
  "#EC4899",
  "#14B8A6",
  "#F97316",
  "#6366F1",
  "#EF4444",
  "#10B981",
  "#A855F7",
  "#F59E0B",
  "#06B6D4",
];

import { mapLeadSourceLabel } from "../brandLabels";

export { mapLeadSourceLabel };

export function mapLeadSources(stats) {
  if (!stats?.lead_source_stats) return [];
  return Object.entries(stats.lead_source_stats)
    .map(([name, count]) => ({
      name: mapLeadSourceLabel(name),
      count: Number(count) || 0,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 12);
}

export function mapStatusBreakdown(stats) {
  if (!stats?.lead_status_stats) return [];
  const colorByName = {
    Cold: "#3B82F6",
    Dormant: "#F97316",
    Warm: "#F59E0B",
    Hot: "#EF4444",
    Qualified: "#10B981",
  };
  const order = ["Qualified", "Hot", "Warm", "Cold", "Dormant"];
  const entries = Object.entries(stats.lead_status_stats)
    .filter(([, v]) => Number(v) > 0)
    .map(([name, value]) => ({
      name,
      value: Number(value) || 0,
      color: colorByName[name] || CHART_COLORS[0],
    }));
  entries.sort((a, b) => {
    const ai = order.indexOf(a.name);
    const bi = order.indexOf(b.name);
    if (ai === -1 && bi === -1) return b.value - a.value;
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
  return entries;
}

export function mapDispositionBreakdown(stats) {
  if (!stats?.disposition_stats) return [];
  return Object.entries(stats.disposition_stats)
    .filter(([, v]) => Number(v) > 0)
    .map(([name, value], idx) => ({
      name,
      value: Number(value) || 0,
      color: CHART_COLORS[idx % CHART_COLORS.length],
    }))
    .sort((a, b) => b.value - a.value);
}

const SKIP_PROJECT_NAMES = new Set(["", "Unknown", "Profiling in Progress"]);

function coerceProjectName(raw) {
  if (raw == null) return "";
  if (typeof raw === "string" || typeof raw === "number") return String(raw).trim();
  if (typeof raw === "object" && raw.name != null) {
    return coerceProjectName(raw.name);
  }
  return "";
}

export function mapProjects(projectList) {
  if (!Array.isArray(projectList)) return [];
  return projectList
    .map((p) => {
      if (typeof p === "string") {
        const name = p.trim();
        return { name, count: 0 };
      }
      const name = coerceProjectName(p?.name ?? p?._id);
      const count = Number(p?.count) || 0;
      return { name, count };
    })
    .filter((p) => p.name && !SKIP_PROJECT_NAMES.has(p.name));
}

/** Normalize /dashboard/projects payload (array legacy or structured object). */
export function parseProjectsPayload(data) {
  if (Array.isArray(data)) {
    return {
      projects: mapProjects(data),
      meta: null,
    };
  }
  if (data && Array.isArray(data.projects)) {
    return {
      projects: mapProjects(data.projects),
      meta: {
        totalLeads: Number(data.total_leads) || 0,
        withProject: Number(data.with_project) || 0,
        otherCount: Number(data.other_count) || 0,
        withoutProject: Number(data.without_project) || 0,
      },
    };
  }
  return { projects: [], meta: null };
}

/** Build AI Calling URL params for disposition chart drill-down. */
export function buildAICallingDrillParams(disposition, timeFilter, projectFilter, dateRange) {
  const params = new URLSearchParams();
  if (disposition) params.set("disposition", disposition);
  const statsParams = buildStatsParams(timeFilter, projectFilter, dateRange);
  if (statsParams.start_date) params.set("start_date", statsParams.start_date);
  if (statsParams.end_date) params.set("end_date", statsParams.end_date);
  return params;
}

/** Build Virtual Customer URL params for dashboard KPI drill-down. */
export function buildVirtualDrillParams(bucket, timeFilter, projectFilter, dateRange) {
  const params = new URLSearchParams();
  params.set("futwork_sync_status", "all");
  const statsParams = buildStatsParams(timeFilter, projectFilter, dateRange);
  if (statsParams.project) params.set("project", statsParams.project);
  if (statsParams.days != null) params.set("days", String(statsParams.days));
  if (statsParams.start_date) params.set("start_date", statsParams.start_date);
  if (statsParams.end_date) params.set("end_date", statsParams.end_date);
  if (bucket) params.set("dashboard_bucket", bucket);
  return params;
}

export const DASHBOARD_BUCKET_LABELS = {
  cold: "Cold Leads",
  dormant: "Dormant Leads",
  hot: "Hot Leads",
  qualified: "Qualified Leads",
  warm: "Warm Leads",
};

export function buildStatsParams(timeFilter, projectFilter, dateRange) {
  const params = {};
  if (projectFilter && projectFilter !== "all") {
    params.project =
      typeof projectFilter === "string" ? projectFilter : coerceProjectName(projectFilter);
  }
  if (timeFilter === "7") params.days = 7;
  else if (timeFilter === "15") params.days = 15;
  else if (timeFilter === "30") params.days = 30;
  else if (timeFilter === "custom" && dateRange?.from) {
    const from = dateRange.from;
    const to = dateRange.to || dateRange.from;
    params.start_date = from.toISOString().slice(0, 10);
    params.end_date = to.toISOString().slice(0, 10);
  }
  return params;
}

export function formatDashboardNumber(num) {
  const n = Number(num);
  if (!Number.isFinite(n)) return "0";
  return n.toLocaleString("en-IN");
}
