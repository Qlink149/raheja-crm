import { memo } from "react";
import {
  ChevronRight,
  Flame,
  Sun,
  Snowflake,
  CheckCircle,
  TrendingDown,
} from "lucide-react";
import { Badge } from "./ui/badge";
import {
  getQualificationBadgeClass,
  getBudgetBadgeClass,
  SYNC_PENDING_BADGE_CLASS,
} from "../lib/leadBadgeStyles";

function PlatformSyncBadge({ status }) {
  const s = (status || "pending").toLowerCase();
  if (s === "pushed") return null;
  if (s === "failed") {
    return (
      <Badge variant="destructive" className="shrink-0">
        Sync Failed
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={`shrink-0 ${SYNC_PENDING_BADGE_CLASS}`}>
      Pending
    </Badge>
  );
}

const getInitials = (name) => {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return parts[0].slice(0, 2).toUpperCase();
};

const getDisplayName = (name) => {
  if (!name || name === "null null" || name === "null") return "Unknown";
  return name;
};

const getLeadQualificationTag = (lead) => {
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
    case "Warm":
      return <Sun className="w-4 h-4 text-orange-400" />;
    case "Dormant":
      return <TrendingDown className="w-4 h-4 text-orange-400" />;
    default:
      return null;
  }
};

const formatBudgetLabel = (lead) => {
  const bucket = (lead?.budget_category || "").trim();
  if (bucket && bucket !== "Other") return bucket;
  const raw = lead?.budget;
  if (raw == null || raw === "" || raw === "0" || raw === 0) return "Budget N/A";
  const num = Number(raw);
  if (Number.isFinite(num) && num > 0) return `₹${num} Cr`;
  return String(raw);
};

const isHniBudget = (lead) => {
  const bucket = (lead?.budget_category || "").trim();
  return bucket === "5 Cr+" || bucket === "2-5 Cr";
};

const LeadCard = memo(function LeadCard({ lead, onSelect }) {
  const qualificationTag = getLeadQualificationTag(lead);

  return (
    <div
      onClick={() => onSelect(lead.id)}
      className="glass-card rounded-lg p-5 cursor-pointer group hover-lift"
      data-testid={`lead-card-${lead.id}`}
    >
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-14 h-14 rounded-full bg-gradient-to-br from-[#C5A059] to-[#8A6D3B] flex items-center justify-center text-black font-semibold text-lg">
          {getInitials(lead.full_name)}
        </div>

        <div className="flex-1 min-w-0 overflow-hidden">
          <div className="flex items-center gap-2 mb-1 min-w-0">
            <h3
              className="lead-card-name truncate flex-1 min-w-0"
              title={getDisplayName(lead.full_name)}
            >
              {getDisplayName(lead.full_name)}
            </h3>
          </div>
          <p className="lead-card-meta text-sm truncate mb-2" title={lead.project || "N/A"}>
            {lead.project || "N/A"}
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            {qualificationTag ? (
              <span className={`flex-shrink-0 ${getQualificationBadgeClass(qualificationTag)}`}>
                {getQualificationIcon(qualificationTag)}
                {qualificationTag}
              </span>
            ) : null}
            <PlatformSyncBadge status={lead.futwork_sync_status} />
            <span
              className={`tabular-nums ${getBudgetBadgeClass(isHniBudget(lead))}`}
              data-testid={`lead-budget-${lead.id}`}
            >
              {formatBudgetLabel(lead)}
            </span>
          </div>
        </div>

        <ChevronRight className="w-5 h-5 text-[#525252] group-hover:text-[#C5A059] transition-colors flex-shrink-0" />
      </div>

      <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-end gap-2 min-w-0">
        <span className="lead-card-footer text-xs truncate">{lead.location_category}</span>
      </div>
    </div>
  );
});

export default LeadCard;
