import { useRef, useState } from "react";
import {
  FileUp,
  Download,
  Info,
  Upload,
  Loader2,
  X as XIcon,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

const TEMPLATE_HEADERS = [
  { key: "Name", required: true, sample: "Sample Customer" },
  { key: "Mobile", required: true, sample: "9999789877" },
];

const TEMPLATE_OPTIONAL_HEADER = {
  key: "Lead ID",
  sample: "optional",
};

const TEMPLATE_CSV =
  "Name,Mobile\n" +
  "Sample Customer,9999789877\n";

const formatSize = (bytes) => {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

const UploadLeadsModal = ({
  open,
  onOpenChange,
  onSubmit,
  uploading = false,
  maxMb = 10,
}) => {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const [batchName, setBatchName] = useState("");

  const validate = (f) => {
    if (!f) return "No file selected";
    if (!f.name.toLowerCase().endsWith(".csv")) return "Only CSV files are supported";
    if (maxMb && f.size > maxMb * 1024 * 1024) return `File too large (max ${maxMb} MB)`;
    return "";
  };

  const handlePick = (f) => {
    const err = validate(f);
    if (err) {
      setError(err);
      setFile(null);
      return;
    }
    setError("");
    setFile(f);
    setBatchName((prev) => {
      if ((prev || "").trim()) return prev;
      const stem = (f.name || "").replace(/\.csv$/i, "").trim();
      return stem.slice(0, 200);
    });
  };

  const handleBrowse = () => inputRef.current?.click();

  const handleInputChange = (e) => {
    const f = e.target.files?.[0];
    if (f) handlePick(f);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!uploading) setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (uploading) return;
    const f = e.dataTransfer?.files?.[0];
    if (f) handlePick(f);
  };

  const handleZoneKeyDown = (e) => {
    if (uploading) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleBrowse();
    }
  };

  const clearFile = () => {
    setFile(null);
    setError("");
    setBatchName("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleUpload = async () => {
    if (!file || uploading) return;
    try {
      await onSubmit(file, { batchName: batchName.trim() });
      clearFile();
      setBatchName("");
      onOpenChange(false);
    } catch {
      // parent already toasted; keep modal open so the user can retry
    }
  };

  const handleOpenChange = (next) => {
    if (uploading) return;
    if (!next) {
      setFile(null);
      setError("");
      setBatchName("");
      if (inputRef.current) inputRef.current.value = "";
    }
    onOpenChange(next);
  };

  const handleDownloadTemplate = () => {
    const blob = new Blob([TEMPLATE_CSV], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "leads_template.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden bg-[#141414] border border-white/10 text-white max-w-2xl p-0">
        <DialogHeader className="shrink-0 px-6 pt-6">
          <DialogTitle className="text-lg font-semibold text-white">
            Add Leads to Campaign
          </DialogTitle>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 pb-6">
          <div className="border-b border-white/10 pb-3">
            <p className="text-sm font-medium text-white/90">Campaign Details</p>
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-[#C5A059] font-semibold">
              Batch name
            </label>
            <Input
              value={batchName}
              onChange={(e) => setBatchName(e.target.value.slice(0, 200))}
              placeholder="e.g. February inbound"
              disabled={uploading}
              className="bg-black/30 border-white/10 text-white placeholder:text-[#525252]"
            />
            <p className="text-xs text-[#737373]">
              Used in upload history; defaults to your CSV file name.
            </p>
          </div>

          {/* Drop zone */}
          <div
            role="button"
            tabIndex={0}
            onClick={!file && !uploading ? handleBrowse : undefined}
            onKeyDown={handleZoneKeyDown}
            onDragOver={handleDragOver}
            onDragEnter={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            aria-label="CSV upload drop zone"
            className={[
              "rounded-lg border-2 border-dashed px-6 py-8 transition-colors outline-none",
              "focus-visible:ring-2 focus-visible:ring-[#C5A059]/50",
              dragOver
                ? "border-[#C5A059]/60 bg-[#C5A059]/5"
                : "border-white/15 bg-white/[0.02] hover:border-white/25",
              uploading ? "opacity-60 cursor-not-allowed" : "cursor-pointer",
            ].join(" ")}
          >
            <div className="flex flex-col items-center text-center gap-3">
              <div className="rounded-lg bg-white/5 p-3">
                <FileUp className="h-6 w-6 text-[#C5A059]" />
              </div>

              {file ? (
                <div className="flex w-full max-w-sm items-center justify-between gap-3 rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-left">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-white" title={file.name}>
                      {file.name}
                    </p>
                    <p className="text-xs text-[#737373]">{formatSize(file.size)}</p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      clearFile();
                    }}
                    disabled={uploading}
                    className="text-[#A3A3A3] hover:text-white disabled:opacity-50"
                    aria-label="Remove selected file"
                  >
                    <XIcon className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <p className="text-sm text-[#A3A3A3]">
                  Drag &amp; drop your file here, or
                </p>
              )}

              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleBrowse();
                  }}
                  disabled={uploading}
                  className="border-white/15 bg-white/[0.04] text-white hover:bg-white/10"
                >
                  Browse
                </Button>
                <span className="text-xs text-[#737373]">File type: CSV</span>
              </div>

              {error && (
                <p className="text-xs text-red-400" role="alert">
                  {error}
                </p>
              )}
            </div>

            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={handleInputChange}
            />
          </div>

          {/* CSV Template Preview */}
          <div className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-medium text-white">CSV Template Preview</p>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={handleDownloadTemplate}
                className="h-8 w-8 text-[#A3A3A3] hover:text-white hover:bg-white/5"
                aria-label="Download CSV template"
                title="Download template"
              >
                <Download className="h-4 w-4" />
              </Button>
            </div>
            <div className="rounded-md border border-white/10 overflow-hidden">
              <div className="grid grid-cols-2 bg-white/[0.03] px-4 py-2 text-xs font-medium text-white">
                {TEMPLATE_HEADERS.map((h) => (
                  <span key={h.key} className="truncate">
                    {h.key}
                    {h.required && <span className="text-red-400">*</span>}
                  </span>
                ))}
              </div>
              <div className="grid grid-cols-2 px-4 py-2 text-xs text-[#A3A3A3] border-t border-white/5">
                {TEMPLATE_HEADERS.map((h) => (
                  <span key={`sample-${h.key}`} className="truncate tabular-nums">
                    {h.sample}
                  </span>
                ))}
              </div>
            </div>
            <p className="mt-2 text-xs text-[#525252]">
              Optional column:{" "}
              <span className="text-[#737373]">{TEMPLATE_OPTIONAL_HEADER.key}</span>{" "}
              (not included in the download template)
            </p>
          </div>

          {/* Important Note */}
          <div className="rounded-lg border border-blue-500/20 bg-blue-500/10 p-4 text-blue-200">
            <div className="flex items-start gap-3">
              <Info className="h-4 w-4 mt-0.5 text-blue-300 flex-shrink-0" />
              <div className="text-sm">
                <p className="font-semibold text-blue-200 mb-1">Important Note !</p>
                <ul className="list-disc pl-5 space-y-1 text-blue-200/90">
                  <li>Only CSV file format is supported with a maximum of 20,000 rows.</li>
                  <li>
                    First row must contain column headers. Aliases accepted (e.g. Lead Id,
                    Mobile Number, Full Name).
                  </li>
                  <li>
                    <span className="text-red-400">Mobile</span> is required (10-digit Indian
                    number). Each mobile is unique — re-uploading the same number updates the
                    existing lead.
                  </li>
                  <li>
                    <span className="text-white">Name</span> is recommended.{" "}
                    <span className="text-white">Lead ID</span> is optional if your CSV includes
                    it.
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter className="shrink-0 flex-row items-center justify-between gap-2 border-t border-white/10 bg-[#101010] px-6 py-4 sm:justify-between sm:space-x-0">
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={uploading}
            className="border-white/15 text-white hover:bg-white/5"
          >
            Close
          </Button>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={clearFile}
              disabled={!file || uploading}
              className="text-[#A3A3A3] hover:text-white hover:bg-white/5 disabled:opacity-50"
            >
              Clear
            </Button>
            <Button
              type="button"
              onClick={handleUpload}
              disabled={!file || uploading}
              className="bg-emerald-600 text-white hover:bg-emerald-500 disabled:bg-emerald-900/40 disabled:text-white/60"
            >
              {uploading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Starting upload…
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  Upload file
                </>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default UploadLeadsModal;
