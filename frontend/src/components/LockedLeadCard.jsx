import { memo } from "react";
import { Lock, MapPin, Building2 } from "lucide-react";
import { Badge } from "./ui/badge";

const getQualificationBadgeClass = (qc) => {
  const v = (qc || "").trim();
  if (v === "Warm") return "bg-orange-500/20 text-orange-300 border border-orange-500/30";
  if (v === "Dormant") return "bg-gray-500/20 text-gray-300 border border-gray-500/30";
  if (v === "Qualified") return "bg-emerald-900/30 text-emerald-300 border border-emerald-500/30";
  if (v === "Hot") return "badge-hot";
  if (v === "Cold") return "badge-cold";
  return "text-[#A3A3A3] bg-white/5 border border-white/5";
};

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
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] z-10 flex flex-col items-center justify-center gap-2 opacity-90 group-hover:opacity-100 transition-opacity">
        <div className="w-10 h-10 rounded-full bg-[#C5A059]/20 flex items-center justify-center">
          <Lock className="text-[#C5A059]" size={18} />
        </div>
        <span className="text-xs text-[#C5A059] font-medium">Premium lead</span>
      </div>

      <div className="relative z-0 pointer-events-none select-none">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center text-[#A1A1AA] text-sm font-semibold flex-shrink-0">
              ?
            </div>
            <div className="min-w-0">
              <p className="text-white font-medium truncate blur-[3px]">{lead.full_name}</p>
              <p className="text-[#737373] text-xs truncate flex items-center gap-1 mt-0.5">
                <Building2 size={12} />
                {lead.project || "Project N/A"}
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-3">
          {lead.disposition ? (
            <Badge className="bg-indigo-900/30 text-indigo-300 border border-indigo-500/30 shrink-0">
              {lead.disposition}
            </Badge>
          ) : null}
          {qualificationTag ? (
            <Badge className={`shrink-0 ${getQualificationBadgeClass(qualificationTag)}`}>
              {qualificationTag}
            </Badge>
          ) : null}
          {lead.budget_category && lead.budget_category !== "Other" ? (
            <Badge variant="outline" className="border-white/10 text-[#A1A1AA] shrink-0">
              {lead.budget_category}
            </Badge>
          ) : null}
        </div>

        <p className="text-[#525252] text-xs flex items-center gap-1">
          <MapPin size={12} />
          {lead.location_category || "Location N/A"}
        </p>
      </div>
    </div>
  );
});

export default LockedLeadCard;
