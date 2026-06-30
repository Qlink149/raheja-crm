import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Users, Lock, Sparkles } from "lucide-react";
import LeadCard from "../components/LeadCard";
import LockedLeadCard from "../components/LockedLeadCard";
import UnlockPremiumModal from "../components/shared/UnlockPremiumModal";
import { LeadGridSkeleton } from "../components/feedback/Skeletons";
import { api } from "../lib/api";
import { BRAND } from "../lib/brandConfig";
import { useColumnCount } from "../hooks/useColumnCount";

const VirtualCustomerPreview = () => {
  const navigate = useNavigate();
  const columnCount = useColumnCount();
  const [loading, setLoading] = useState(true);
  const [unlocked, setUnlocked] = useState([]);
  const [lockedTeasers, setLockedTeasers] = useState([]);
  const [meta, setMeta] = useState(null);
  const [unlockModalOpen, setUnlockModalOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await api.get("/virtual-customer/preview");
        if (cancelled) return;
        setUnlocked(res.data?.unlocked || []);
        setLockedTeasers(res.data?.locked_teasers || []);
        setMeta(res.data?.meta || null);
      } catch (err) {
        console.error("Failed to load VC preview:", err);
        toast.error("Failed to load Virtual Customer preview");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const gridItems = useMemo(() => {
    const items = [
      ...unlocked.map((lead) => ({ type: "unlocked", lead })),
      ...lockedTeasers.map((lead) => ({ type: "locked", lead })),
    ];
    return items;
  }, [unlocked, lockedTeasers]);

  const rows = useMemo(() => {
    const result = [];
    for (let i = 0; i < gridItems.length; i += columnCount) {
      result.push(gridItems.slice(i, i + columnCount));
    }
    return result;
  }, [gridItems, columnCount]);

  const handleLeadSelect = (leadId) => {
    navigate(`/customer/${leadId}`);
  };

  const dispositionLabel = meta?.disposition_filter || "Site Visit";
  const totalMatching = meta?.total_matching ?? 0;
  const unlockedLimit = meta?.unlocked_limit ?? 5;

  return (
    <motion.div className="space-y-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="glass-card rounded-xl p-5 border border-[#C5A059]/25 bg-gradient-to-r from-[#C5A059]/10 to-transparent">
        <div className="flex flex-wrap items-start gap-4 justify-between">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#C5A059]/20 flex items-center justify-center flex-shrink-0">
              <Sparkles className="text-[#C5A059]" size={20} />
            </div>
            <div>
              <p className="page-kicker text-xs mb-1">
                Preview mode
              </p>
              <h1 className="page-title text-2xl">Virtual Customer</h1>
              <p className="page-subtitle text-sm mt-1 max-w-2xl">
                Preview: {unlockedLimit} of{" "}
                <span className="lead-card-name font-medium tabular-nums">
                  {totalMatching.toLocaleString()}
                </span>{" "}
                {dispositionLabel} leads · {BRAND.supportMessage}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setUnlockModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[#C5A059]/40 text-[#C5A059] text-sm hover:bg-[#C5A059]/10 transition-colors"
          >
            <Lock size={16} />
            Unlock all leads
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 lead-card-meta px-1">
        <Users className="w-4 h-4" />
        <span className="text-sm">
          <span className="text-[#C5A059] font-semibold">{dispositionLabel}</span> pipeline
          {!loading && (
            <>
              {" "}
              · <span className="tabular-nums">{unlocked.length}</span> unlocked ·{" "}
              <span className="tabular-nums">{Math.max(0, totalMatching - unlocked.length)}</span>{" "}
              locked
            </>
          )}
        </span>
      </div>

      {loading ? (
        <LeadGridSkeleton count={9} />
      ) : gridItems.length === 0 ? (
        <div className="glass-card rounded-xl p-12 text-center">
          <p className="lead-card-name font-medium mb-2">No {dispositionLabel} leads yet</p>
          <p className="page-subtitle text-sm">
            When AI calls produce {dispositionLabel} dispositions, preview leads will appear here.
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {rows.map((row, rowIdx) => (
            <div
              key={`preview-row-${rowIdx}`}
              className="grid gap-4"
              style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }}
            >
              {row.map((item) =>
                item.type === "unlocked" ? (
                  <LeadCard
                    key={item.lead.id}
                    lead={item.lead}
                    onSelect={handleLeadSelect}
                  />
                ) : (
                  <LockedLeadCard
                    key={item.lead.id}
                    lead={item.lead}
                    onUnlock={() => setUnlockModalOpen(true)}
                  />
                )
              )}
            </div>
          ))}
        </div>
      )}

      {!loading && lockedTeasers.length > 0 && totalMatching > unlockedLimit && (
        <p className="text-center lead-card-footer text-xs pb-4">
          +{Math.max(0, totalMatching - unlockedLimit - lockedTeasers.length).toLocaleString()}{" "}
          more {dispositionLabel} leads available after unlock
        </p>
      )}

      <UnlockPremiumModal
        open={unlockModalOpen}
        onOpenChange={setUnlockModalOpen}
        title="Unlock Virtual Customer"
      />
    </motion.div>
  );
};

export default VirtualCustomerPreview;
