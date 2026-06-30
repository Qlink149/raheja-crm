import { memo } from "react";
import { Lock, MapPin, Building2 } from "lucide-react";
import { Badge } from "./ui/badge";
import { getQualificationBadgeClass } from "../lib/leadBadgeStyles";
import { getDispositionBadgeClass } from "../lib/callBadgeStyles";

const LockedLeadCard = memo(function LockedLeadCard({ lead, onUnlock }) {
  const qualificationTag = (lead?.qualification_category || "").trim();

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onUnlock}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onUnlock();
        }
      }}
      className="glass-card rounded-xl p-5 relative overflow-hidden cursor-pointer group border border-white/10 hover:border-[#C5A059]/30 transition-all"
      data-testid={`locked-lead-card-${lead.id}`}
    >
      <div className="locked-lead-overlay absolute inset-0 backdrop-blur-[2px] z-10 flex flex-col items-center justify-center gap-2 opacity-90 group-hover:opacity-100 transition-opacity">
        <div className="w-10 h-10 rounded-full bg-[#C5A059]/20 flex items-center justify-center">
          <Lock className="text-[#C5A059]" size={18} />
        </div>
        <span className="text-xs text-[#C5A059] font-medium">Premium lead</span>
      </div>

      <div className="relative z-0 pointer-events-none select-none">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center lead-card-meta text-sm font-semibold flex-shrink-0">
              ?
            </div>
            <div className="min-w-0">
              <p className="lead-card-name truncate blur-[3px]">{lead.full_name}</p>
              <p className="lead-card-meta text-xs truncate flex items-center gap-1 mt-0.5">
                <Building2 size={12} />
                {lead.project || "Project N/A"}
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-3">
          {lead.disposition ? (
            <span className={`shrink-0 ${getDispositionBadgeClass(lead.disposition)}`}>
              {lead.disposition}
            </span>
          ) : null}
          {qualificationTag ? (
            <span className={`shrink-0 ${getQualificationBadgeClass(qualificationTag)}`}>
              {qualificationTag}
            </span>
          ) : null}
          {lead.budget_category && lead.budget_category !== "Other" ? (
            <Badge variant="outline" className="lead-badge lead-badge--budget shrink-0">
              {lead.budget_category}
            </Badge>
          ) : null}
        </div>

        <p className="lead-card-footer text-xs flex items-center gap-1">
          <MapPin size={12} />
          {lead.location_category || "Location N/A"}
        </p>
      </div>
    </div>
  );
});

export default LockedLeadCard;
