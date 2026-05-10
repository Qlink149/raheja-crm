import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  Phone,
  PhoneCall,
  Clock,
  Calendar,
  User,
  Play,
  Pause,
  X,
  ChevronDown,
  Filter,
  Search,
  FileText,
  CheckCircle,
  XCircle,
  AlertCircle,
  PhoneOff,
  PhoneMissed,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";

const AICallingPage = ({ onLogout, currentUser }) => {
  const [calls, setCalls] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState("all");
  const [selectedCall, setSelectedCall] = useState(null);
  const [showCallDetail, setShowCallDetail] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dispositionFilter, setDispositionFilter] = useState("all");
  const [updatingDisposition, setUpdatingDisposition] = useState(false);
  
  // Audio player state
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const audioRef = useRef(null);

  useEffect(() => {
    fetchCallHistory();
    // Fetch ALL calls once — filter and search are applied client-side.
    // This eliminates race conditions between rapidly-changing filters and
    // the network response order.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchCallHistory = async () => {
    setLoading(true);
    try {
      const response = await api.get("/call-history");
      setCalls(response.data.calls || []);
      setCampaigns(response.data.campaigns || []);
    } catch (error) {
      console.error("Error fetching call history:", error);
      toast.error("Failed to load call history");
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return "0s";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "N/A";
    const date = new Date(dateStr);
    return date.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getDispositionBadge = (disposition) => {
    const styles = {
      "Interested": "bg-emerald-900/30 text-emerald-300 border-emerald-500/30",
      "Not Interested": "bg-red-900/30 text-red-300 border-red-500/30",
      "Busy": "bg-yellow-900/30 text-yellow-300 border-yellow-500/30",
      "Dropped": "bg-orange-900/30 text-orange-300 border-orange-500/30",
      "Incomplete conversation": "bg-gray-900/30 text-gray-300 border-gray-500/30",
    };
    return styles[disposition] || "bg-gray-900/30 text-gray-300 border-gray-500/30";
  };

  const getStatusBadge = (status) => {
    const styles = {
      "completed": "bg-emerald-900/30 text-emerald-300",
      "no-answer": "bg-yellow-900/30 text-yellow-300",
      "busy": "bg-orange-900/30 text-orange-300",
      "failed": "bg-red-900/30 text-red-300",
    };
    return styles[status] || "bg-gray-900/30 text-gray-300";
  };

  const getStatusIcon = (status) => {
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

  const handlePlayPause = () => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
      } else {
        audioRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setAudioProgress(audioRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setAudioDuration(audioRef.current.duration);
    }
  };

  const handleSeek = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    if (audioRef.current) {
      audioRef.current.currentTime = percent * audioDuration;
    }
  };

  const updateDisposition = async (call, newDisposition) => {
    if (!call?.lead_id) return;
    setUpdatingDisposition(true);
    try {
      await api.patch(`/leads/${call.lead_id}/disposition`, {
        disposition: newDisposition,
      });
      toast.success(`Marked as ${newDisposition}`);
      // Update local state so UI reflects change immediately
      setCalls((prev) =>
        prev.map((c) =>
          c.lead_id === call.lead_id ? { ...c, disposition: newDisposition } : c
        )
      );
      setSelectedCall((prev) =>
        prev && prev.lead_id === call.lead_id
          ? { ...prev, disposition: newDisposition }
          : prev
      );
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update disposition");
    } finally {
      setUpdatingDisposition(false);
    }
  };

  // Normalise text for comparison: lowercase + collapse whitespace.
  const normText = (s) => (s || "").toString().toLowerCase().replace(/\s+/g, " ").trim();
  // Digits-only helper for phone matching.
  const digitsOnly = (s) => (s || "").toString().replace(/\D+/g, "");

  // Single client-side filter pipeline — no race conditions, no stale state.
  const filteredCalls = calls.filter((call) => {
    // Campaign filter (exact, case-insensitive)
    if (selectedCampaign && selectedCampaign !== "all") {
      if (normText(call.campaign) !== normText(selectedCampaign)) return false;
    }
    // Status filter (case-insensitive on call.status OR lead-level fields)
    if (statusFilter && statusFilter !== "all") {
      if (normText(call.status) !== normText(statusFilter)) return false;
    }
    // Disposition filter (case-insensitive)
    if (dispositionFilter && dispositionFilter !== "all") {
      if (normText(call.disposition) !== normText(dispositionFilter)) return false;
    }
    // Search filter (name OR phone, with phone-digits normalisation)
    const raw = (searchQuery || "").trim();
    if (raw) {
      const qText = normText(raw);
      const qDigits = digitsOnly(raw);
      const name = normText(call.customer_name);
      const phoneDigits = digitsOnly(call.phone);
      const nameMatch = qText && name.includes(qText);
      const phoneMatch =
        qDigits &&
        (phoneDigits.includes(qDigits) || phoneDigits.slice(-10).includes(qDigits));
      if (!nameMatch && !phoneMatch) return false;
    }
    return true;
  });

  // Stats reflect the currently-filtered view (consistent with the table)
  const totalCalls = filteredCalls.length;
  const completedCalls = filteredCalls.filter(c => normText(c.status) === 'completed').length;
  const interestedCalls = filteredCalls.filter(c => normText(c.disposition) === 'interested').length;
  const avgDuration = filteredCalls.length > 0
    ? Math.round(filteredCalls.reduce((sum, c) => sum + (c.duration || 0), 0) / filteredCalls.length)
    : 0;

  return (
    <div className="min-h-screen bg-[#0D0D0D] flex">
      <Sidebar onLogout={onLogout} currentUser={currentUser} />
      
      <main className="flex-1 p-8 ml-20 lg:ml-64">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="font-serif text-3xl text-white mb-2">
            AI Calling Campaign
          </h1>
          <p className="text-[#A3A3A3]">
            View all AI calls made for Rustomjee campaigns
          </p>
        </motion.div>

        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-xl p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="p-3 bg-[#C5A059]/20 rounded-lg flex-shrink-0">
                <PhoneCall className="w-5 h-5 text-[#C5A059]" />
              </div>
              <span className="text-xs uppercase tracking-widest text-[#C5A059] whitespace-nowrap">
                Total Calls
              </span>
            </div>
            <p className="text-3xl font-serif text-white">{totalCalls}</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card rounded-xl p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="p-3 bg-emerald-900/30 rounded-lg flex-shrink-0">
                <CheckCircle className="w-5 h-5 text-emerald-400" />
              </div>
              <span className="text-xs uppercase tracking-widest text-emerald-400 whitespace-nowrap">
                Completed
              </span>
            </div>
            <p className="text-3xl font-serif text-white">{completedCalls}</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card rounded-xl p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="p-3 bg-blue-900/30 rounded-lg flex-shrink-0">
                <User className="w-5 h-5 text-blue-400" />
              </div>
              <span className="text-xs uppercase tracking-widest text-blue-400 whitespace-nowrap">
                Interested
              </span>
            </div>
            <p className="text-3xl font-serif text-white">{interestedCalls}</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="glass-card rounded-xl p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="p-3 bg-purple-900/30 rounded-lg flex-shrink-0">
                <Clock className="w-5 h-5 text-purple-400" />
              </div>
              <span className="text-xs uppercase tracking-widest text-purple-400 whitespace-nowrap">
                Avg Duration
              </span>
            </div>
            <p className="text-3xl font-serif text-white">{formatDuration(avgDuration)}</p>
          </motion.div>
        </div>

        {/* Filters */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass-card rounded-xl p-4 mb-6"
        >
          <div className="flex items-center gap-4 flex-wrap">
            {/* Campaign Filter */}
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-[#C5A059]" />
              <Select value={selectedCampaign} onValueChange={setSelectedCampaign}>
                <SelectTrigger className="w-[200px] bg-[#1A1A1A] border-white/10 text-white">
                  <SelectValue placeholder="All Campaigns" />
                </SelectTrigger>
                <SelectContent className="bg-[#1A1A1A] border-white/10">
                  <SelectItem value="all">All Campaigns</SelectItem>
                  {campaigns.map((campaign) => (
                    <SelectItem key={campaign} value={campaign}>
                      {campaign}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Status Filter */}
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[150px] bg-[#1A1A1A] border-white/10 text-white">
                <SelectValue placeholder="All Status" />
              </SelectTrigger>
              <SelectContent className="bg-[#1A1A1A] border-white/10">
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="no-answer">No Answer</SelectItem>
                <SelectItem value="busy">Busy</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>

            {/* Disposition Filter */}
            <Select value={dispositionFilter} onValueChange={setDispositionFilter}>
              <SelectTrigger className="w-[180px] bg-[#1A1A1A] border-white/10 text-white">
                <SelectValue placeholder="All Dispositions" />
              </SelectTrigger>
              <SelectContent className="bg-[#1A1A1A] border-white/10">
                <SelectItem value="all">All Dispositions</SelectItem>
                <SelectItem value="Interested">Interested</SelectItem>
                <SelectItem value="Not Interested">Not Interested</SelectItem>
                <SelectItem value="Busy">Busy</SelectItem>
                <SelectItem value="Dropped">Dropped</SelectItem>
                <SelectItem value="Incomplete conversation">Incomplete</SelectItem>
              </SelectContent>
            </Select>

            {/* Search */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
              <Input
                placeholder="Search by name or phone..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-[#1A1A1A] border-white/10 text-white placeholder:text-[#525252]"
              />
            </div>
          </div>
        </motion.div>

        {/* Call History Table */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass-card rounded-xl overflow-hidden"
        >
          <div className="p-4 border-b border-white/10">
            <h2 className="text-lg font-semibold text-white">Call History</h2>
            <p className="text-sm text-[#A3A3A3]">
              {filteredCalls.length} calls found
            </p>
          </div>

          <ScrollArea className="h-[500px]">
            {/* Header row — CSS grid replaces <table> to avoid ve-dynamic span injection */}
            <div className="grid grid-cols-7 gap-2 px-4 py-3 bg-[#1A1A1A] sticky top-0 border-b border-white/10">
              {["Customer","Phone","Timestamp","Duration","Disposition","Status","Action"].map((h) => (
                <span key={h} className="text-xs uppercase tracking-wider text-[#C5A059] font-semibold">{h}</span>
              ))}
            </div>

            {/* Data rows */}
            <div className="divide-y divide-white/5">
              {loading ? (
                <div className="px-4 py-8 text-center text-[#A3A3A3]">
                  Loading call history...
                </div>
              ) : filteredCalls.length === 0 ? (
                <div className="px-4 py-8 text-center text-[#A3A3A3]">
                  No calls found
                </div>
              ) : (
                filteredCalls.map((call, index) => (
                  <div
                    key={call.id ? `${call.id}-${index}` : `idx-${index}`}
                    className="grid grid-cols-7 gap-2 px-4 py-4 hover:bg-white/5 cursor-pointer transition-colors items-center"
                    onClick={() => {
                      setSelectedCall(call);
                      setShowCallDetail(true);
                      setIsPlaying(false);
                      setAudioProgress(0);
                    }}
                  >
                    {/* Customer */}
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#C5A059] to-[#8A6D3B] flex items-center justify-center text-black text-xs font-semibold flex-shrink-0">
                        {call.customer_name ? call.customer_name.charAt(0).toUpperCase() : "?"}
                      </div>
                      <span className="text-white text-sm truncate">{call.customer_name || "Unknown"}</span>
                    </div>

                    {/* Phone */}
                    <span className="text-[#A3A3A3] text-sm font-mono truncate">{call.phone || "N/A"}</span>

                    {/* Timestamp */}
                    <span className="text-[#A3A3A3] text-sm">{formatDate(call.created_at)}</span>

                    {/* Duration */}
                    <span className="text-[#C5A059] text-sm font-medium">{formatDuration(call.duration)}</span>

                    {/* Disposition */}
                    <div>
                      {call.disposition && (
                        <span className={`px-2 py-1 rounded text-xs border ${getDispositionBadge(call.disposition)}`}>
                          {call.disposition}
                        </span>
                      )}
                    </div>

                    {/* Status */}
                    <div>
                      <span className={`px-2 py-1 rounded text-xs flex items-center gap-1 w-fit ${getStatusBadge(call.status)}`}>
                        {getStatusIcon(call.status)}
                        {call.status}
                      </span>
                    </div>

                    {/* Action */}
                    <div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-[#C5A059] hover:text-[#E5C585] hover:bg-[#C5A059]/10"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedCall(call);
                          setShowCallDetail(true);
                        }}
                      >
                        View Details
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </motion.div>

        {/* Call Detail Dialog */}
        <Dialog open={showCallDetail} onOpenChange={setShowCallDetail}>
          <DialogContent className="bg-[#1A1A1A] border-white/10 max-w-3xl max-h-[90vh] overflow-hidden">
            <DialogHeader>
              <DialogTitle className="text-white flex items-center gap-3">
                <PhoneCall className="w-5 h-5 text-[#C5A059]" />
                Call Details
                <span className="text-[#A3A3A3] text-sm font-normal">
                  | {selectedCall?.customer_name || "Unknown"}
                </span>
              </DialogTitle>
            </DialogHeader>

            {selectedCall && (
              <div className="space-y-6 overflow-y-auto max-h-[70vh] pr-2">
                {/* Call Summary */}
                <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                  <h3 className="text-sm uppercase tracking-wider text-[#C5A059] mb-4 flex items-center gap-2">
                    <Phone className="w-4 h-4" />
                    Call Summary
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-xs text-[#525252] mb-1">Status</p>
                      <span className={`px-2 py-1 rounded text-xs inline-flex items-center gap-1 ${getStatusBadge(selectedCall.status)}`}>
                        {getStatusIcon(selectedCall.status)}
                        {selectedCall.status}
                      </span>
                    </div>
                    <div>
                      <p className="text-xs text-[#525252] mb-1">Duration</p>
                      <p className="text-[#C5A059] font-medium">
                        {formatDuration(selectedCall.duration)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-[#525252] mb-1">Disposition</p>
                      {selectedCall.disposition ? (
                        <span className={`px-2 py-1 rounded text-xs border ${getDispositionBadge(selectedCall.disposition)}`}>
                          {selectedCall.disposition}
                        </span>
                      ) : (
                        <p className="text-[#A3A3A3]">N/A</p>
                      )}
                    </div>
                    <div>
                      <p className="text-xs text-[#525252] mb-1">Call Date</p>
                      <p className="text-white text-sm">
                        {formatDate(selectedCall.created_at)}
                      </p>
                    </div>
                  </div>

                  {/* Disposition quick-toggle */}
                  <div className="mt-4 pt-4 border-t border-white/10 flex flex-wrap items-center gap-2">
                    <span className="text-xs uppercase tracking-wider text-[#525252] mr-2">
                      Re-classify Lead:
                    </span>
                    <Button
                      data-testid="mark-interested-btn"
                      size="sm"
                      disabled={selectedCall.disposition === "Interested" || updatingDisposition}
                      onClick={() => updateDisposition(selectedCall, "Interested")}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40"
                    >
                      {updatingDisposition ? "..." : "Mark Interested"}
                    </Button>
                    <Button
                      data-testid="mark-not-interested-btn"
                      size="sm"
                      disabled={selectedCall.disposition === "Not Interested" || updatingDisposition}
                      onClick={() => updateDisposition(selectedCall, "Not Interested")}
                      className="bg-red-700 hover:bg-red-600 text-white disabled:opacity-40"
                    >
                      {updatingDisposition ? "..." : "Mark Not Interested"}
                    </Button>
                  </div>
                </div>

                {/* Audio Player */}
                {selectedCall.recording_url && (
                  <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                    <h3 className="text-sm uppercase tracking-wider text-[#C5A059] mb-4 flex items-center gap-2">
                      <Play className="w-4 h-4" />
                      Call Recording
                    </h3>
                    <div className="flex items-center gap-4">
                      <Button
                        size="icon"
                        onClick={handlePlayPause}
                        className="w-12 h-12 rounded-full bg-[#C5A059] hover:bg-[#E5C585] text-black"
                      >
                        {isPlaying ? (
                          <Pause className="w-5 h-5" />
                        ) : (
                          <Play className="w-5 h-5 ml-1" />
                        )}
                      </Button>
                      
                      <div className="flex-1">
                        <div
                          className="h-2 bg-white/10 rounded-full cursor-pointer"
                          onClick={handleSeek}
                        >
                          <div
                            className="h-full bg-[#C5A059] rounded-full"
                            style={{ width: `${(audioProgress / audioDuration) * 100 || 0}%` }}
                          />
                        </div>
                        <div className="flex justify-between mt-1">
                          <span className="text-xs text-[#A3A3A3]">
                            {formatDuration(Math.floor(audioProgress))}
                          </span>
                          <span className="text-xs text-[#A3A3A3]">
                            {formatDuration(Math.floor(audioDuration))}
                          </span>
                        </div>
                      </div>
                    </div>
                    
                    <audio
                      ref={audioRef}
                      src={selectedCall.recording_url}
                      onTimeUpdate={handleTimeUpdate}
                      onLoadedMetadata={handleLoadedMetadata}
                      onEnded={() => setIsPlaying(false)}
                    />
                  </div>
                )}

                {/* Tabs for Details and Transcript */}
                <Tabs defaultValue="details" className="w-full">
                  <TabsList className="bg-white/5 border border-white/10">
                    <TabsTrigger value="details" className="data-[state=active]:bg-[#C5A059] data-[state=active]:text-black">
                      Details
                    </TabsTrigger>
                    <TabsTrigger value="transcript" className="data-[state=active]:bg-[#C5A059] data-[state=active]:text-black">
                      Transcript
                    </TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="details" className="mt-4">
                    <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-[#525252] mb-1">Phone Number</p>
                          <p className="text-white font-mono">{selectedCall.phone || "N/A"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-[#525252] mb-1">Customer Name</p>
                          <p className="text-white">{selectedCall.customer_name || "Unknown"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-[#525252] mb-1">Lead ID</p>
                          <p className="text-white font-mono text-sm">{selectedCall.lead_id || "N/A"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-[#525252] mb-1">Campaign</p>
                          <p className="text-white">{selectedCall.campaign || "N/A"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-[#525252] mb-1">Direction</p>
                          <p className="text-white capitalize">{selectedCall.direction || "Outbound"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-[#525252] mb-1">Hangup By</p>
                          <p className="text-white capitalize">{selectedCall.hangup_by || "N/A"}</p>
                        </div>
                      </div>
                    </div>
                  </TabsContent>
                  
                  <TabsContent value="transcript" className="mt-4">
                    <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                      <h4 className="text-sm text-[#C5A059] mb-4 flex items-center gap-2">
                        <FileText className="w-4 h-4" />
                        Call Transcript
                      </h4>
                      {selectedCall.transcript ? (
                        <ScrollArea className="h-[300px]">
                          <div className="space-y-3">
                            {selectedCall.transcript.split('\n').map((line, idx) => {
                              const isAgent = line.toLowerCase().startsWith('assistant:') || line.toLowerCase().startsWith('ai:');
                              const isUser = line.toLowerCase().startsWith('user:') || line.toLowerCase().startsWith('customer:');
                              const cleanLine = line.replace(/^(assistant|user|ai|customer):/i, '').trim();
                              
                              if (!cleanLine) return null;
                              
                              return (
                                <div
                                  key={idx}
                                  className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                                >
                                  <div
                                    className={`max-w-[80%] rounded-lg px-4 py-2 ${
                                      isUser
                                        ? 'bg-white/10 text-white'
                                        : 'bg-[#C5A059]/20 text-[#C5A059]'
                                    }`}
                                  >
                                    <p className="text-xs mb-1 opacity-70">
                                      {isUser ? 'Customer' : 'AI Agent'}
                                    </p>
                                    <p className="text-sm">{cleanLine}</p>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </ScrollArea>
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
      </main>
    </div>
  );
};

// Render call rows directly inside the table tbody. The tbody carries
// x-excluded="true" so the visual-edits babel plugin does NOT wrap the
// dynamic .map() expression with <span data-ve-dynamic>; that wrapper would
// otherwise become an invalid child of <tbody>, get hoisted out by the
// browser parser, and break React's row reconciliation on filter changes.
//
// Reference: /app/frontend/plugins/visual-edits/babel-metadata-plugin.js
// line ~1719 — children-wrapping is skipped when x-excluded or
// data-ve-dynamic is present on the opening element.

export default AICallingPage;
