import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { api, getApiBase } from "../lib/api";

const LeadUploadDetailsModal = ({ open, onOpenChange, uploadId, onUpdated }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);
  const [editName, setEditName] = useState("");

  useEffect(() => {
    if (!open || !uploadId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await api.get(
          `/campaigns/current/upload-history/${encodeURIComponent(uploadId)}/details`
        );
        if (!cancelled) {
          setDetail(res.data || null);
          setEditName((res.data?.batch_name || "").trim());
        }
      } catch (e) {
        if (!cancelled) {
          toast.error(e?.response?.data?.detail || "Could not load upload details");
          setDetail(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, uploadId]);

  const base = getApiBase();

  const handleRename = async () => {
    const name = editName.trim();
    if (!name || !uploadId) return;
    setSaving(true);
    try {
      await api.patch(
        `/campaigns/current/upload-history/${encodeURIComponent(uploadId)}`,
        { batch_name: name }
      );
      toast.success("Batch name updated");
      onUpdated?.();
      const res = await api.get(
        `/campaigns/current/upload-history/${encodeURIComponent(uploadId)}/details`
      );
      setDetail(res.data || null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Rename failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1A1A1A] border-white/10 text-white max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-white">Upload details</DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-8 text-[#A3A3A3]">
            <Loader2 className="h-8 w-8 animate-spin text-[#C5A059]" />
          </div>
        ) : detail ? (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-2 text-[#A3A3A3]">
              <span>Batch name</span>
              <span className="text-white">{detail.batch_name || "—"}</span>
              <span>File</span>
              <span className="text-white break-all">{detail.filename || "—"}</span>
              <span>Rows</span>
              <span className="text-white">{detail.row_count ?? "—"}</span>
              <span>Processed</span>
              <span className="text-[#C5A059]">{detail.processed ?? "—"}</span>
              <span>Unprocessed</span>
              <span className="text-white">{detail.unprocessed ?? "—"}</span>
            </div>

            <div className="space-y-2">
              <p className="text-xs uppercase tracking-wider text-[#C5A059]">Rename batch</p>
              <div className="flex gap-2">
                <Input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="bg-black/30 border-white/10 text-white"
                  placeholder="Batch name"
                />
                <Button
                  type="button"
                  onClick={handleRename}
                  disabled={saving || !editName.trim()}
                  className="bg-[#C5A059] text-black hover:bg-[#E5C585] shrink-0"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              {detail.original_csv_secure_url ? (
                <a
                  href={`${base}/campaigns/current/upload-history/${encodeURIComponent(uploadId)}/download-original`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center rounded-md border border-[#C5A059]/40 bg-transparent px-4 py-2 text-sm font-medium text-[#C5A059] hover:bg-[#C5A059]/10"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Original CSV
                </a>
              ) : null}
              {detail.has_unprocessed_csv ? (
                <a
                  href={`${base}/campaigns/current/upload-history/${encodeURIComponent(uploadId)}/unprocessed.csv`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center rounded-md border border-white/20 bg-transparent px-4 py-2 text-sm font-medium text-white hover:bg-white/10"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Unprocessed rows
                </a>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="text-[#737373] py-4">No data</p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            className="border-white/15 text-white"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default LeadUploadDetailsModal;
