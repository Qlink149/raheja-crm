import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { campaignsAPI } from "../lib/api";
import { UI_COPY } from "../lib/brandLabels";

const PRESETS = [100, 200, 1000, 3000];
const MAX_LIMIT = 5000;

const BulkFutworkPushModal = ({
  open,
  onOpenChange,
  eligibleCount = 0,
  futworkEnabled = false,
  onStarted,
}) => {
  const [batchName, setBatchName] = useState("");
  const [preset, setPreset] = useState(100);
  const [useCustom, setUseCustom] = useState(false);
  const [customLimit, setCustomLimit] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setBatchName("");
    setPreset(100);
    setUseCustom(false);
    setCustomLimit("");
  }, [open]);

  const limit = useMemo(() => {
    if (useCustom) {
      const n = parseInt(String(customLimit).trim(), 10);
      return Number.isFinite(n) ? n : 0;
    }
    return preset;
  }, [useCustom, customLimit, preset]);

  const cappedLimit = Math.min(limit, MAX_LIMIT, eligibleCount || MAX_LIMIT);
  const canSubmit =
    futworkEnabled &&
    batchName.trim().length > 0 &&
    limit >= 1 &&
    limit <= MAX_LIMIT &&
    limit <= eligibleCount &&
    !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const res = await campaignsAPI.startBulkFutworkPush({
        batch_name: batchName.trim(),
        limit,
      });
      const d = res.data || {};
      toast.success(
        `Batch "${batchName.trim()}" started (${d.requested ?? limit} leads). Runs in the background.`
      );
      onOpenChange(false);
      onStarted?.(d.batch_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start bulk push");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1A1A1A] border-white/10 text-white max-w-md">
        <DialogHeader>
          <DialogTitle className="text-white">{UI_COPY.pushDbToCallingEngine}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <p className="text-[#A3A3A3]">
            <span className="text-white font-medium tabular-nums">{eligibleCount}</span>{" "}
            leads ready (valid 10-digit phone, not yet synced). Large batches run in the
            background and may take a long time.
          </p>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-[#C5A059]">Batch name</label>
            <Input
              value={batchName}
              onChange={(e) => setBatchName(e.target.value)}
              maxLength={200}
              placeholder="e.g. May DB push 1"
              className="bg-black/30 border-white/10 text-white"
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wider text-[#C5A059]">How many leads</p>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((n) => (
                <Button
                  key={n}
                  type="button"
                  size="sm"
                  variant={!useCustom && preset === n ? "default" : "outline"}
                  className={
                    !useCustom && preset === n
                      ? "bg-[#C5A059] text-black hover:bg-[#E5C585]"
                      : "border-white/10 text-white hover:bg-white/5"
                  }
                  disabled={n > eligibleCount}
                  onClick={() => {
                    setUseCustom(false);
                    setPreset(n);
                  }}
                >
                  {n}
                </Button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant={useCustom ? "default" : "outline"}
                className={
                  useCustom
                    ? "bg-[#C5A059] text-black hover:bg-[#E5C585]"
                    : "border-white/10 text-white hover:bg-white/5"
                }
                onClick={() => setUseCustom(true)}
              >
                Custom
              </Button>
              {useCustom ? (
                <Input
                  type="number"
                  min={1}
                  max={Math.min(MAX_LIMIT, eligibleCount)}
                  value={customLimit}
                  onChange={(e) => setCustomLimit(e.target.value)}
                  placeholder={`1–${Math.min(MAX_LIMIT, eligibleCount)}`}
                  className="bg-black/30 border-white/10 text-white w-32"
                />
              ) : null}
            </div>
            {limit > eligibleCount && eligibleCount > 0 ? (
              <p className="text-amber-400 text-xs">Max available: {eligibleCount}</p>
            ) : null}
          </div>

          {!futworkEnabled ? (
            <p className="text-red-400 text-xs">{UI_COPY.callingEngineNotConfigured}</p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            className="border-white/15 text-white"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!canSubmit}
            className="bg-[#C5A059] text-black hover:bg-[#E5C585]"
            onClick={handleSubmit}
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Starting…
              </>
            ) : (
              `Push ${cappedLimit > 0 ? cappedLimit : limit} leads`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default BulkFutworkPushModal;
