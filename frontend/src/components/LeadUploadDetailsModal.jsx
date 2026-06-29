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
import { api, downloadAuthenticatedFile } from "../lib/api";

const LeadUploadDetailsModal = ({ open, onOpenChange, uploadId, onUpdated }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);
  const [editName, setEditName] = useState("");
  const [downloadingOriginal, setDownloadingOriginal] = useState(false);
  const [downloadingUnprocessed, setDownloadingUnprocessed] = useState(false);

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

  const originalCsvFilename = () => {
    const base = (detail?.batch_name || detail?.filename || "upload").trim();
    const safe = base.replace(/[^\w.\-]+/g, "_").replace(/^_+|_+$/g, "") || "upload";
    return safe.toLowerCase().endsWith(".csv") ? safe : `${safe}.csv`;
  };

  const handleDownloadOriginal = async () => {
    if (!uploadId) return;
    setDownloadingOriginal(true);
    try {
      await downloadAuthenticatedFile(
        `/campaigns/current/upload-history/${encodeURIComponent(uploadId)}/download-original`,
        originalCsvFilename()
      );
    } catch (e) {
      toast.error(e?.message || e?.response?.data?.detail || "Could not download original CSV");
    } finally {
      setDownloadingOriginal(false);
    }
  };

  const handleDownloadUnprocessed = async () => {
    if (!uploadId) return;
    setDownloadingUnprocessed(true);
    try {
      const stem = (detail?.batch_name || "upload").trim().replace(/[^\w.\-]+/g, "_") || "upload";
      await downloadAuthenticatedFile(
        `/campaigns/current/upload-history/${encodeURIComponent(uploadId)}/unprocessed.csv`,
        `${stem}_unprocessed.csv`
      );
    } catch (e) {
      toast.error(e?.message || e?.response?.data?.detail || "Could not download unprocessed rows");
    } finally {
      setDownloadingUnprocessed(false);
    }
  };

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
            {detail.status === "processing" ? (
              <div className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-200 text-xs">
                <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                This batch is still processing. Stats will update when complete.
              </div>
            ) : null}
            {detail.source === "bulk_push" ? (
              <p className="text-[#A3A3A3] text-xs rounded border border-violet-500/20 bg-violet-500/10 px-3 py-2">
                This batch was created from a DB bulk Calling Engine push (no CSV file).
              </p>
            ) : null}
            <div className="grid grid-cols-2 gap-2 text-[#A3A3A3]">
              <span>Batch name</span>
              <span className="text-white">{detail.batch_name || "—"}</span>
              <span>File</span>
              <span className="text-white break-all">{detail.filename || "—"}</span>
              <span>Rows</span>
              <span className="text-white">{detail.row_count ?? "—"}</span>
              <span>Processed</span>
              <span className="text-[#C5A059]">
                {detail.status === "processing" ? (
                  <span className="inline-flex items-center gap-1 text-amber-300">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Processing…
                  </span>
                ) : (
                  detail.processed ?? "—"
                )}
              </span>
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
              {detail.source !== "bulk_push" && detail.original_csv_secure_url ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={downloadingOriginal}
                  onClick={handleDownloadOriginal}
                  className="border-[#C5A059]/40 text-[#C5A059] hover:bg-[#C5A059]/10"
                >
                  {downloadingOriginal ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4 mr-2" />
                  )}
                  Original CSV
                </Button>
              ) : null}
              {detail.source !== "bulk_push" && detail.has_unprocessed_csv ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={downloadingUnprocessed}
                  onClick={handleDownloadUnprocessed}
                  className="border-white/20 text-white hover:bg-white/10"
                >
                  {downloadingUnprocessed ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4 mr-2" />
                  )}
                  Unprocessed rows
                </Button>
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
