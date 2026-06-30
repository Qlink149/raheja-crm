import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Phone,
  PhoneCall,
  Play,
  Pause,
  FileText,
  CheckCircle,
  XCircle,
  AlertCircle,
  PhoneMissed,
} from "lucide-react";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { api } from "../lib/api";
import { parseCallTranscriptTurns, WHITELABEL_AGENT_LABEL } from "../utils/callTranscript";
import { formatDateTimeIST } from "../lib/dateUtils";
import { getDispositionBadgeClass, getStatusBadgeClass } from "../lib/callBadgeStyles";

const formatDuration = (seconds) => {
  if (!seconds) return "0s";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
};

const formatDate = (dateStr) => formatDateTimeIST(dateStr);

const StatusIcon = ({ status }) => {
  switch (status) {
    case "completed":
      return <CheckCircle className="w-4 h-4" />;
    case "no-answer":
      return <PhoneMissed className="w-4 h-4" />;
    case "busy":
      return <AlertCircle className="w-4 h-4" />;
    case "failed":
      return <XCircle className="w-4 h-4" />;
    default:
      return <Phone className="w-4 h-4" />;
  }
};

const CallDetailDialog = ({ open, onOpenChange, call, onDispositionChange }) => {
  const navigate = useNavigate();
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [updatingDisposition, setUpdatingDisposition] = useState(false);

  const handleOpenChange = (next) => {
    if (!next) {
      setIsPlaying(false);
      setAudioProgress(0);
      if (audioRef.current) audioRef.current.pause();
    }
    onOpenChange(next);
  };

  const handlePlayPause = useCallback(() => {
    if (audioRef.current) {
      if (isPlaying) audioRef.current.pause();
      else audioRef.current.play();
      setIsPlaying(!isPlaying);
    }
  }, [isPlaying]);

  const handleTimeUpdate = useCallback(() => {
    if (audioRef.current) setAudioProgress(audioRef.current.currentTime);
  }, []);

  const handleLoadedMetadata = useCallback(() => {
    if (audioRef.current) setAudioDuration(audioRef.current.duration);
  }, []);

  const handleSeek = useCallback(
    (e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const percent = (e.clientX - rect.left) / rect.width;
      if (audioRef.current) audioRef.current.currentTime = percent * audioDuration;
    },
    [audioDuration]
  );

  const updateDisposition = async (targetCall, newDisposition) => {
    if (!targetCall?.lead_id) return;
    setUpdatingDisposition(true);
    try {
      await api.patch(`/leads/${targetCall.lead_id}/disposition`, {
        disposition: newDisposition,
      });
      toast.success(`Marked as ${newDisposition}`);
      onDispositionChange?.(targetCall, newDisposition);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update disposition");
    } finally {
      setUpdatingDisposition(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="surface-elevated max-w-3xl w-[calc(100vw-2rem)] h-[min(90vh,820px)] p-0 overflow-hidden flex flex-col gap-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-white/10 flex-shrink-0">
          <DialogTitle className="flex items-center gap-3 text-base">
            <PhoneCall className="w-5 h-5 text-[#C5A059]" />
            <span>Call Details</span>
            <span className="text-[#A3A3A3] text-sm font-normal truncate">
              · {call?.customer_name || "Unknown"}
            </span>
          </DialogTitle>
        </DialogHeader>

        {call && (
          <div className="flex-1 min-h-0 overflow-y-auto scrollbar-luxe px-6 py-5 space-y-6">
            <div className="bg-white/5 rounded-lg p-4 border border-white/10">
              <h3 className="kicker mb-4 flex items-center gap-2">
                <Phone className="w-4 h-4" />
                Call Summary
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="min-w-0">
                  <p className="text-xs text-[#525252] mb-1">Status</p>
                  <span
                    className={`inline-flex items-center gap-1 ${getStatusBadgeClass(
                      call.status
                    )}`}
                  >
                    <StatusIcon status={call.status} />
                    <span className="capitalize">{call.status}</span>
                  </span>
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-[#525252] mb-1">Duration</p>
                  <p className="text-[#C5A059] font-medium tabular-nums">
                    {formatDuration(call.duration)}
                  </p>
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-[#525252] mb-1">Disposition</p>
                  {call.disposition ? (
                    <span
                      className={`inline-block truncate max-w-full ${getDispositionBadgeClass(
                        call.disposition
                      )}`}
                    >
                      {call.disposition}
                    </span>
                  ) : (
                    <p className="text-[#A3A3A3]">N/A</p>
                  )}
                </div>
                <div className="min-w-[11rem]">
                  <p className="text-xs text-[#525252] mb-1">Call Date</p>
                  <p className="text-white text-sm tabular-nums whitespace-nowrap">
                    {formatDate(call.created_at)}
                  </p>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-white/10 flex flex-wrap items-center gap-2">
                <span className="text-xs uppercase tracking-wider text-[#525252] mr-2">
                  Re-classify Lead:
                </span>
                <Button
                  data-testid="mark-interested-btn"
                  size="sm"
                  disabled={call.disposition === "Interested" || updatingDisposition}
                  onClick={() => updateDisposition(call, "Interested")}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 btn-tactile"
                >
                  {updatingDisposition ? "..." : "Mark Interested"}
                </Button>
                <Button
                  data-testid="mark-not-interested-btn"
                  size="sm"
                  disabled={call.disposition === "Not Interested" || updatingDisposition}
                  onClick={() => updateDisposition(call, "Not Interested")}
                  className="bg-red-700 hover:bg-red-600 text-white disabled:opacity-40 btn-tactile"
                >
                  {updatingDisposition ? "..." : "Mark Not Interested"}
                </Button>
              </div>
            </div>

            {call.recording_url && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h3 className="kicker mb-4 flex items-center gap-2">
                  <Play className="w-4 h-4" />
                  Call Recording
                </h3>
                <div className="flex items-center gap-4">
                  <Button
                    size="icon"
                    onClick={handlePlayPause}
                    className="w-12 h-12 rounded-full bg-[#C5A059] hover:bg-[#E5C585] text-black btn-tactile flex-shrink-0"
                  >
                    {isPlaying ? (
                      <Pause className="w-5 h-5" />
                    ) : (
                      <Play className="w-5 h-5 ml-1" />
                    )}
                  </Button>

                  <div className="flex-1 min-w-0">
                    <div
                      className="h-2 bg-white/10 rounded-full cursor-pointer relative overflow-hidden"
                      onClick={handleSeek}
                    >
                      <div
                        className="absolute inset-y-0 left-0 bg-gradient-to-r from-[#C5A059] to-[#E5C585] rounded-full transition-all duration-150"
                        style={{
                          width: `${(audioProgress / audioDuration) * 100 || 0}%`,
                        }}
                      />
                    </div>
                    <div className="flex justify-between mt-1">
                      <span className="text-xs text-[#A3A3A3] tabular-nums">
                        {formatDuration(Math.floor(audioProgress))}
                      </span>
                      <span className="text-xs text-[#A3A3A3] tabular-nums">
                        {formatDuration(Math.floor(audioDuration))}
                      </span>
                    </div>
                  </div>
                </div>

                <audio
                  ref={audioRef}
                  src={call.recording_url}
                  onTimeUpdate={handleTimeUpdate}
                  onLoadedMetadata={handleLoadedMetadata}
                  onEnded={() => setIsPlaying(false)}
                />
              </div>
            )}

            <Tabs defaultValue="details" className="w-full flex flex-col min-h-0">
              <TabsList className="bg-white/5 border border-white/10 flex-shrink-0">
                <TabsTrigger
                  value="details"
                  className="data-[state=active]:bg-[#C5A059] data-[state=active]:text-black transition-all duration-300"
                >
                  Details
                </TabsTrigger>
                <TabsTrigger
                  value="transcript"
                  className="data-[state=active]:bg-[#C5A059] data-[state=active]:text-black transition-all duration-300"
                >
                  Transcript
                </TabsTrigger>
              </TabsList>

              <TabsContent value="details" className="mt-4">
                <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Phone Number</p>
                      <p className="text-white font-mono tabular-nums truncate">
                        {call.phone || "N/A"}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Customer Name</p>
                      <p className="text-white truncate">{call.customer_name || "Unknown"}</p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Lead ID</p>
                      <p className="text-white font-mono text-sm truncate">
                        {call.lead_id || "N/A"}
                      </p>
                      {!call.lead_id && call.phone ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="mt-2 border-[#C5A059]/40 text-[#C5A059] hover:bg-[#C5A059]/10"
                          onClick={() => {
                            const q = new URLSearchParams({
                              search: call.phone,
                              futwork_sync_status: "all",
                            });
                            navigate(`/virtual-customer?${q.toString()}`);
                          }}
                        >
                          Find in Virtual Customer
                        </Button>
                      ) : null}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Campaign</p>
                      <p className="text-white truncate">{call.campaign || "N/A"}</p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Direction</p>
                      <p className="text-white capitalize">{call.direction || "Outbound"}</p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252] mb-1">Hangup By</p>
                      <p className="text-white capitalize">{call.hangup_by || "N/A"}</p>
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="transcript" className="mt-4">
                <div className="bg-white/5 rounded-lg p-4 border border-white/10 flex flex-col">
                  <h4 className="kicker mb-4 flex flex-shrink-0 items-center gap-2">
                    <FileText className="w-4 h-4" />
                    Call Transcript
                  </h4>
                  {call.transcript ? (
                    <div className="max-h-[55vh] min-h-[200px] overflow-y-auto pr-1 scrollbar-luxe">
                      <div className="flex flex-col gap-3 w-full pr-2">
                        {parseCallTranscriptTurns(call.transcript).map((turn, idx) => (
                          <div
                            key={`${idx}-${turn.isUser ? "c" : "a"}-${turn.text.slice(0, 40)}`}
                            className={`flex w-full shrink-0 ${
                              turn.isUser ? "justify-end" : "justify-start"
                            }`}
                          >
                            <div
                              className={`max-w-[85%] rounded-lg px-4 py-2 overflow-hidden ${
                                turn.isUser
                                  ? "bg-white/10 text-white"
                                  : "bg-[#C5A059]/15 text-[#F2D9A8] border border-[#C5A059]/20"
                              }`}
                            >
                              <p className="text-xs mb-1 opacity-70">
                                {turn.isUser ? "Customer" : WHITELABEL_AGENT_LABEL}
                              </p>
                              <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
                                {turn.text}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="text-[#A3A3A3] text-center py-8">
                      No transcript available for this call
                    </p>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default CallDetailDialog;
