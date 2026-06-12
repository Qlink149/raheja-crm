import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  Phone,
  MessageCircle,
  Crown,
  MapPin,
  Building2,
  Building,
  Briefcase,
  Home,
  Calendar,
  Target,
  Wallet,
  Ruler,
  Clock,
  User,
  MessageSquare,
  PhoneCall,
  Sparkles,
  Send,
  Bot,
  History,
  Users,
  // FileText, — CONTEXT_UPDATES_HIDDEN
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { ScrollArea } from "../components/ui/scroll-area";
import EmptyState from "../components/feedback/EmptyState";
import { CustomerDetailSkeleton } from "../components/feedback/Skeletons";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { formatDateTimeIST } from "../lib/dateUtils";
import { formatDuration } from "../lib/formatDuration";
// CONTEXT_UPDATES_HIDDEN — re-enable when context timeline is fixed
// import { buildContextUpdatesFromLeadAndCalls } from "../lib/contextUpdates";
import { mapLeadSourceLabel } from "../lib/brandLabels";
import {
  canExpandCallSummary,
  callSummaryDisabledReason,
  formatLeadBudgetDisplay,
  isUsableCallSummary,
} from "../lib/leadBudgetDisplay";
import CallRecordingPlayer from "../components/CallRecordingPlayer";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";

const SALES_QUALIFICATION_OPTIONS = ["Cold Qualified", "Warm Lead", "Hot Lead"];

const CustomerDetailPage = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const [lead, setLead] = useState(null);
  const [loading, setLoading] = useState(true);
  const [leadCalls, setLeadCalls] = useState([]);
  const [callsLoading, setCallsLoading] = useState(true);
  const [salesReps, setSalesReps] = useState([]);
  const [qualifying, setQualifying] = useState(false);

  useEffect(() => {
    fetchLeadDetail();
  }, [id]);

  useEffect(() => {
    if (!isAdmin) return;
    api.get("/users/sales-reps").then((r) => setSalesReps(r.data || [])).catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    setCallsLoading(true);
    (async () => {
      try {
        const res = await api.get(`/leads/${id}/calls`);
        if (!mounted) return;
        setLeadCalls(res.data?.calls || []);
      } catch {
        if (mounted) setLeadCalls([]);
      } finally {
        if (mounted) setCallsLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [id]);

  const fetchLeadDetail = async () => {
    try {
      const response = await api.get(`/leads/${id}`);
      setLead(response.data);
    } catch (error) {
      console.error("Error fetching lead:", error);
      toast.error("Failed to load customer details");
    } finally {
      setLoading(false);
    }
  };

  const getInitials = (name) => {
    if (!name || name === "Unknown" || name === "") return "?";
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  // Helper to display value or N/A
  const displayValue = (val) => {
    if (!val || val === "" || val === "Profiling in Progress") return "N/A";
    return val;
  };

  // Helper to get display name
  const getDisplayName = () => {
    if (!lead?.full_name || lead.full_name === "Unknown" || lead.full_name === "") {
      return "Unknown Customer";
    }
    return lead.full_name;
  };

  const handleSalesQualification = async (value) => {
    setQualifying(true);
    try {
      await api.patch(`/leads/${id}/sales-qualification`, {
        sales_qualification: value === "none" ? "" : value,
      });
      setLead((prev) => ({
        ...prev,
        sales_qualification: value === "none" ? "" : value,
      }));
      toast.success("Lead qualification updated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to update qualification");
    } finally {
      setQualifying(false);
    }
  };

  const handleAssign = async (userId) => {
    if (!userId || userId === "none") return;
    try {
      await api.patch(`/leads/${id}/assign`, { assigned_user_id: userId });
      await fetchLeadDetail();
      toast.success("Lead assigned");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Assignment failed");
    }
  };

  const openAICalling = () => {
    const phone = lead?.mobile_digits || lead?.mobile || "";
    const params = new URLSearchParams({ leadId: id });
    if (phone) params.set("phone", phone);
    navigate(`/ai-calling?${params.toString()}`);
  };

  const handleWhatsAppClick = () => {
    const customerName = lead?.first_name && lead.first_name !== "" ? lead.first_name : "there";
    const projectName = lead?.project && lead.project !== "" ? lead.project : "our premium properties";
    const message = encodeURIComponent(
      `Hello ${customerName}! I'm reaching out from Rustomjee regarding ${projectName}. Based on your interest, I'd love to share some exciting options that match your preferences. Would you be available for a quick call?`
    );
    window.open(`https://wa.me/?text=${message}`, "_blank");
    toast.success("WhatsApp message prepared!", {
      description: "Opening WhatsApp with personalized message",
    });
  };

  const handleAICallClick = () => {
    const displayName = getDisplayName();
    toast.success("AI Call Initiated!", {
      description: `Connecting to ${displayName}...`,
      duration: 3000,
    });
  };

  /* CONTEXT_UPDATES_HIDDEN — re-enable when context timeline is fixed
  const contextUpdates = useMemo(() => {
    if (!lead) return [];
    const stored = lead.context_updates;
    if (Array.isArray(stored) && stored.length > 0) return stored;
    return buildContextUpdatesFromLeadAndCalls(lead, leadCalls);
  }, [lead, leadCalls]);

  const getContextIcon = (type) => {
    switch (type) {
      case 'call':
        return <PhoneCall className="w-4 h-4 text-[#C5A059]" />;
      case 'whatsapp':
        return <MessageCircle className="w-4 h-4 text-emerald-400" />;
      case 'human':
        return <User className="w-4 h-4 text-blue-400" />;
      default:
        return <FileText className="w-4 h-4 text-[#C5A059]" />;
    }
  };

  const getContextIconBg = (type) => {
    switch (type) {
      case 'call':
        return 'bg-[#C5A059]/20 border-[#C5A059]/30';
      case 'whatsapp':
        return 'bg-emerald-900/30 border-emerald-800/50';
      case 'human':
        return 'bg-blue-900/30 border-blue-800/50';
      default:
        return 'bg-white/10 border-white/20';
    }
  };
  */

  if (loading) {
    return (
      <motion.div className="space-y-8">

          <div className="max-w-7xl mx-auto">
            <CustomerDetailSkeleton />
          </div>
      </motion.div>
    );
  }

  if (!lead) {
    return (
      <motion.div className="space-y-8">

          <EmptyState
            icon={User}
            title="Customer not found"
            description="This lead may have been removed or merged. Head back to the customer list and try again."
            action={{
              label: "Back to Customers",
              onClick: () => navigate("/virtual-customer"),
              icon: ArrowLeft,
            }}
          />
      </motion.div>
    );
  }

  return (
    <motion.div className="space-y-8">

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="max-w-7xl mx-auto"
        >
          <motion.button
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            onClick={() => navigate("/virtual-customer")}
            className="flex items-center gap-2 text-[#A1A1AA] hover:text-white mb-4 transition-colors"
            data-testid="back-to-customers-btn"
          >
            <ArrowLeft size={18} />
            Back to Explorer
          </motion.button>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="relative rounded-xl overflow-hidden h-20 mb-6"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-[#0A0A0A] via-[#1A1A1A] to-[#C5A059]/20" />
            <div className="relative z-10 h-full flex items-center px-6">
              <Building className="text-[#C5A059] mr-4" size={24} />
              <div>
                <p className="text-[#C5A059] font-serif text-lg">{lead.project || "No Project Assigned"}</p>
                <p className="text-[#52525B] text-xs">{mapLeadSourceLabel(lead.source)} · {lead.status || "Inquiry"}</p>
              </div>
            </div>
          </motion.div>

          {/* Hero Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-xl p-8 mb-6"
          >
            <div className="flex flex-col lg:flex-row gap-8 min-w-0">
              {/* Avatar Section */}
              <div className="flex flex-col items-center lg:items-start flex-shrink-0">
                <div className="w-32 h-32 rounded-full bg-gradient-to-br from-[#C5A059] to-[#8A6D3B] flex items-center justify-center text-black text-4xl font-serif mb-4 shadow-xl">
                  {getInitials(lead.full_name)}
                </div>

              </div>

              {/* Profile Details */}
              <div className="flex-1 min-w-0">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-6 min-w-0">
                  <div className="min-w-0">
                    <h1 className="font-serif text-3xl text-white mb-2 tracking-tight truncate">
                      {getDisplayName()}
                    </h1>
                    <p className="text-[#A3A3A3] truncate">
                      {displayValue(lead.designation) !== "N/A"
                        ? lead.designation
                        : "Professional"}
                      {displayValue(lead.ethnicity) !== "N/A" && ` • ${lead.ethnicity}`}
                    </p>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex gap-3">
                    <Button
                      data-testid="whatsapp-btn"
                      onClick={handleWhatsAppClick}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-2"
                    >
                      <MessageCircle className="w-4 h-4" />
                      Send WhatsApp
                    </Button>
                    <Button
                      data-testid="ai-call-btn"
                      onClick={handleAICallClick}
                      className="bg-[#C5A059] hover:bg-[#E5C585] text-black flex items-center gap-2"
                    >
                      <Phone className="w-4 h-4" />
                      Trigger AI Call
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={openAICalling}
                      className="border-white/20 text-white hover:bg-white/10"
                    >
                      <History className="w-4 h-4 mr-2" />
                      AI Calling
                    </Button>
                  </div>
                </div>

                <div className="flex flex-wrap gap-4 mb-6 items-end">
                  <div className="min-w-[200px]">
                    <p className="text-xs text-[#525252] mb-1">Sales qualification</p>
                    <Select
                      value={lead.sales_qualification || "none"}
                      onValueChange={handleSalesQualification}
                      disabled={qualifying}
                    >
                      <SelectTrigger className="bg-black/30 border-white/10 text-white">
                        <SelectValue placeholder="Not qualified" />
                      </SelectTrigger>
                      <SelectContent className="bg-[#1A1A1A] border-white/10">
                        <SelectItem value="none">Not set</SelectItem>
                        {SALES_QUALIFICATION_OPTIONS.map((opt) => (
                          <SelectItem key={opt} value={opt}>
                            {opt}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {isAdmin && (
                    <div className="min-w-[200px]">
                      <p className="text-xs text-[#525252] mb-1">Assigned to</p>
                      <Select
                        value={lead.assigned_user_id || "none"}
                        onValueChange={handleAssign}
                      >
                        <SelectTrigger className="bg-black/30 border-white/10 text-white">
                          <SelectValue placeholder="Unassigned" />
                        </SelectTrigger>
                        <SelectContent className="bg-[#1A1A1A] border-white/10">
                          <SelectItem value="none">Unassigned</SelectItem>
                          {salesReps.map((rep) => (
                            <SelectItem key={rep.id} value={rep.id}>
                              {rep.full_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  {!isAdmin && lead.assigned_to && (
                    <p className="text-sm text-[#A3A3A3]">Assigned to: {lead.assigned_to}</p>
                  )}
                </div>

                {/* Quick Info Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 min-w-0">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-2 bg-white/5 rounded-lg flex-shrink-0">
                      <MapPin className="w-4 h-4 text-[#C5A059]" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252]">Location</p>
                      <p
                        className="text-sm text-white truncate"
                        title={displayValue(
                          lead.current_residential_location ||
                            lead.current_residence_location ||
                            lead.location ||
                            (lead.location_category &&
                            lead.location_category !== "Other" &&
                            lead.location_category !== "Profiling in Progress"
                              ? lead.location_category
                              : "")
                        )}
                      >
                        {displayValue(
                          lead.current_residential_location ||
                            lead.current_residence_location ||
                            lead.location ||
                            (lead.location_category &&
                            lead.location_category !== "Other" &&
                            lead.location_category !== "Profiling in Progress"
                              ? lead.location_category
                              : "")
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-2 bg-white/5 rounded-lg flex-shrink-0">
                      <Home className="w-4 h-4 text-[#C5A059]" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252]">Residence Type</p>
                      <p className="text-sm text-white truncate" title={displayValue(lead.current_residence_type)}>
                        {displayValue(lead.current_residence_type)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-2 bg-white/5 rounded-lg flex-shrink-0">
                      <Building2 className="w-4 h-4 text-[#C5A059]" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252]">Project Interest</p>
                      <p className="text-sm text-white truncate" title={displayValue(lead.project)}>
                        {displayValue(lead.project)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-2 bg-white/5 rounded-lg flex-shrink-0">
                      <Target className="w-4 h-4 text-[#C5A059]" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[#525252]">Intent</p>
                      <p className="text-sm text-white truncate" title={lead.intent_category || "N/A"}>
                        {lead.intent_category || "N/A"}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Content Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-w-0">
            {/* AI Persona Summary & Strategic Next Move */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="lg:col-span-5 space-y-6 min-w-0"
            >
              {/* AI Persona Summary */}
              <AIInsightCard
                icon={Sparkles}
                title="AI Persona Summary"
                cachedValue={lead.aiPersonaSummary}
                fallback=""
                endpoint={`/leads/${id}/persona-summary`}
                fieldKey="summary"
                isMarkdown
                onUpdated={(val) => setLead((prev) => prev ? { ...prev, aiPersonaSummary: val } : prev)}
              />

              {/* Strategic Next Move */}
              <AIInsightCard
                icon={Target}
                title="Strategic Next Move"
                cachedValue={lead.strategicNextMove}
                fallback=""
                endpoint={`/leads/${id}/strategic-next-move`}
                fieldKey="recommendation"
                highlight
                onUpdated={(val) => setLead((prev) => prev ? { ...prev, strategicNextMove: val } : prev)}
              />

              {/* Data DNA */}
              <div className="glass-card rounded-xl p-6">
                <h2 className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold mb-6">
                  Data DNA
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <DataDNAItem
                    icon={Wallet}
                    label="Budget"
                    value={formatLeadBudgetDisplay(lead)}
                  />
                  <DataDNAItem
                    icon={Ruler}
                    label="Carpet Area"
                    value={lead.carpet_area}
                  />
                  <DataDNAItem
                    icon={Home}
                    label="Configuration"
                    value={lead.configuration || lead.bhk || ""}
                  />
                  <DataDNAItem
                    icon={Clock}
                    label="Possession"
                    value={lead.possession_requirement}
                  />
                  <DataDNAItem
                    icon={MapPin}
                    label="Location Pref"
                    value={
                      lead.location ||
                      (lead.location_category &&
                      lead.location_category !== "Other" &&
                      lead.location_category !== "Profiling in Progress"
                        ? lead.location_category
                        : "")
                    }
                  />
                  <DataDNAItem
                    icon={Target}
                    label="Purpose"
                    value={lead.reason_for_purchase}
                  />
                </div>
              </div>
            </motion.div>

            {/* Interaction Timeline (Context Updates hidden — search CONTEXT_UPDATES_HIDDEN) */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="lg:col-span-7 glass-card rounded-xl p-6 min-w-0 flex flex-col overflow-hidden"
            >
              <h2 className="kicker mb-6 flex-shrink-0">Interaction Timeline</h2>
              <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
                <CallsTimeline calls={leadCalls} loading={callsLoading} />
              </div>
            </motion.div>

            {/* CONTEXT_UPDATES_HIDDEN — re-enable when context timeline is fixed
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="glass-card rounded-xl p-6 min-w-0 flex flex-col"
            >
              <div className="flex items-center gap-2 mb-6 flex-shrink-0">
                <History className="w-5 h-5 text-[#C5A059]" />
                <h2 className="kicker">Context Updates</h2>
              </div>

              <ScrollArea className="h-80 lg:h-96 w-full pr-2">
                <div className="relative pr-2">
                  <div className="absolute left-[18px] top-0 bottom-0 w-px bg-white/10" />

                  <div className="space-y-4">
                    {contextUpdates.map((update, index) => (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.1 }}
                        className="relative flex gap-4 pl-1 min-w-0"
                      >
                        <div className={`relative z-10 flex-shrink-0 w-9 h-9 rounded-full border flex items-center justify-center ${getContextIconBg(update.type)}`}>
                          {getContextIcon(update.type)}
                        </div>

                        <div className="flex-1 pb-4 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="text-xs font-mono text-[#C5A059] tabular-nums">{update.date}</span>
                            <span className="text-xs text-[#525252]">
                              {update.type === 'call' ? 'Call' : update.type === 'whatsapp' ? 'WhatsApp' : 'Agent'}
                            </span>
                          </div>
                          <p className="text-sm text-[#A3A3A3] leading-relaxed break-words">
                            {update.context.replace(/Profiling in Progress/g, 'property details')}
                          </p>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </ScrollArea>
            </motion.div>
            */}
          </div>
        </motion.div>
    </motion.div>
  );
};

// Helper Component
const DataDNAItem = ({ icon: Icon, label, value }) => {
  // Filter out "Profiling in Progress" and treat it as empty
  const displayVal = (value && value !== "" && value !== "Profiling in Progress") ? value : "";
  
  return (
    <div className="p-4 bg-white/5 rounded-lg border border-white/5 hover:border-[#C5A059]/30 transition-colors overflow-hidden">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-4 h-4 text-[#C5A059] flex-shrink-0" strokeWidth={1.5} />
        <span className="text-xs text-[#525252] uppercase tracking-wider truncate">{label}</span>
      </div>
      <p className="text-white text-sm font-medium truncate" title={displayVal || "N/A"}>
        {displayVal || "N/A"}
      </p>
    </div>
  );
};

// AI-driven insight card with cached value + Refresh button (used for Persona Summary & Strategic Next Move)
const AIInsightCard = ({ icon: Icon, title, cachedValue, fallback, endpoint, fieldKey, highlight, isMarkdown, onUpdated }) => {
  const [content, setContent] = useState(cachedValue || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setContent(cachedValue || "");
  }, [cachedValue]);

  // Auto-generate on mount if no cache and we have data to work with
  useEffect(() => {
    if (!cachedValue && !fallback) {
      generate(false);
    }
    if (!cachedValue && fallback) {
      setContent(fallback);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const generate = async (refresh) => {
    setLoading(true);
    setError("");
    try {
      const res = await api.post(`${endpoint}${refresh ? "?refresh=true" : ""}`);
      const value = res.data?.[fieldKey] || "";
      setContent(value);
      onUpdated && onUpdated(value);
    } catch (e) {
      const msg = e?.response?.data?.detail || "Failed to generate. Please try again.";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const cardClasses = highlight
    ? "glass-card rounded-xl p-6 border-[#C5A059]/30"
    : "glass-card rounded-xl p-6";
  const bodyClasses = highlight
    ? "bg-[#C5A059]/10 rounded-lg p-4 border border-[#C5A059]/20 text-white"
    : "text-[#A3A3A3]";

  return (
    <div className={cardClasses}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Icon className="w-5 h-5 text-[#C5A059]" />
          <h2 className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold">
            {title}
          </h2>
        </div>
        <button
          data-testid={`refresh-${title.toLowerCase().replace(/\s+/g, "-")}-btn`}
          onClick={() => generate(true)}
          disabled={loading}
          className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-[#C5A059] hover:text-[#E5C585] disabled:opacity-50 transition-colors"
          title="Regenerate with GPT-4o"
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" />
          )}
          Refresh
        </button>
      </div>
      <div className={bodyClasses}>
        {loading && !content ? (
          <div className="flex items-center gap-2 text-[#A3A3A3] text-sm">
            <Loader2 className="w-4 h-4 animate-spin text-[#C5A059]" />
            Analysing transcript with GPT-4o…
          </div>
        ) : error ? (
          <p className="text-red-300 text-sm">{error}</p>
        ) : content ? (
          isMarkdown ? (
            <MarkdownLite text={content} />
          ) : (
            <p className="leading-relaxed whitespace-pre-line">{content}</p>
          )
        ) : (
          <p className="leading-relaxed text-sm">{fallback || "No data available."}</p>
        )}
      </div>
    </div>
  );
};

// Tiny markdown renderer — supports bold (**text**), bullets (- item), and paragraphs.
const MarkdownLite = ({ text }) => {
  const renderInline = (line) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((p, i) => {
      if (/^\*\*[^*]+\*\*$/.test(p)) {
        return (
          <strong key={i} className="text-[#C5A059] font-semibold">
            {p.slice(2, -2)}
          </strong>
        );
      }
      return <span key={i}>{p}</span>;
    });
  };
  const lines = text.split("\n");
  const blocks = [];
  let bullets = [];
  const flushBullets = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="list-disc pl-5 space-y-1 mb-2">
          {bullets.map((b, i) => (
            <li key={i} className="text-sm leading-relaxed">{renderInline(b)}</li>
          ))}
        </ul>
      );
      bullets = [];
    }
  };
  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushBullets();
      return;
    }
    if (trimmed.startsWith("- ")) {
      bullets.push(trimmed.slice(2));
    } else {
      flushBullets();
      blocks.push(
        <p key={`p-${idx}`} className="text-sm leading-relaxed mb-2">
          {renderInline(trimmed)}
        </p>
      );
    }
  });
  flushBullets();
  return <div>{blocks}</div>;
};

// Calls timeline — replaces the previous Tabs (WhatsApp + Calls) UI.
const CallsTimeline = ({ calls, loading }) => {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[#A3A3A3] text-sm">
        <Loader2 className="w-4 h-4 animate-spin text-[#C5A059]" />
        Loading calls…
      </div>
    );
  }

  if (!calls?.length) {
    return <p className="text-sm text-[#A3A3A3]">No call interactions yet for this customer.</p>;
  }

  return (
    <ScrollArea className="h-[min(60vh,640px)] lg:h-[min(75vh,800px)] w-full pr-2">
      <div className="space-y-4 pr-3 pb-2">
        {calls.map((call) => (
          <CallCard key={call.call_sid || `${call.lead_id}-${call.call_date}`} call={call} />
        ))}
      </div>
    </ScrollArea>
  );
};

const formatCallDate = (call) => {
  const raw = call?.created_at || call?.call_date;
  if (!raw) return "Unknown date";
  return formatDateTimeIST(raw);
};

const dispositionStyle = (disposition, status) => {
  const d = (disposition || "").toLowerCase();
  const s = (status || "").toLowerCase();
  if (d === "interested") return "bg-emerald-900/30 text-emerald-300 border-emerald-500/30";
  if (d === "not interested") return "bg-red-900/30 text-red-300 border-red-500/30";
  if (d === "busy" || s === "busy") return "bg-yellow-900/30 text-yellow-300 border-yellow-500/30";
  if (d === "dropped") return "bg-orange-900/30 text-orange-300 border-orange-500/30";
  if (s === "completed") return "bg-emerald-900/30 text-emerald-300 border-emerald-500/30";
  if (s === "no-answer") return "bg-zinc-800/60 text-zinc-300 border-white/10";
  if (s === "failed") return "bg-red-900/30 text-red-300 border-red-500/30";
  return "bg-white/5 text-[#A3A3A3] border-white/10";
};

const CallCard = ({ call }) => {
  const canExpand = canExpandCallSummary(call);
  const cachedSummary = isUsableCallSummary(call.ai_call_summary)
    ? call.ai_call_summary.trim()
    : "";
  const [expanded, setExpanded] = useState(false);
  const [summary, setSummary] = useState(cachedSummary);
  const [loading, setLoading] = useState(false);

  const label = call.disposition || call.status || "Unknown";
  const disabledReason = callSummaryDisabledReason(call);

  const toggle = async () => {
    if (!canExpand) return;
    const next = !expanded;
    setExpanded(next);
    if (!next) return;

    if (cachedSummary) {
      setSummary(cachedSummary);
      return;
    }

    if (!summary && !loading) {
      setLoading(true);
      try {
        const params = { refresh: true };
        if (call.call_sid) params.call_sid = call.call_sid;
        const res = await api.post(`/leads/${call.lead_id}/call-summary`, null, { params });
        setSummary(res.data?.summary || "Summary unavailable.");
      } catch (e) {
        setSummary(e?.response?.data?.detail || "Summary unavailable.");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="bg-white/5 rounded-lg border border-white/5 min-w-0">
      <div className="p-4 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-3 min-w-0">
          <div className="flex items-center gap-2 text-xs text-[#A3A3A3] min-w-0">
            <PhoneCall className="w-3.5 h-3.5 text-[#C5A059] flex-shrink-0" />
            <span className="tabular-nums truncate">{formatCallDate(call)}</span>
            {call.duration > 0 ? (
              <span className="text-[#C5A059] tabular-nums flex-shrink-0">{formatDuration(call.duration)}</span>
            ) : null}
          </div>
          <span className={`px-2 py-0.5 rounded text-[11px] border flex-shrink-0 ${dispositionStyle(call.disposition, call.status)}`}>
            {label}
          </span>
        </div>

        <CallRecordingPlayer
          src={call.recording_url}
          testId={`call-audio-${call.lead_id}`}
        />

        {/* AI Summary toggle */}
        <button
          type="button"
          onClick={toggle}
          disabled={!canExpand}
          title={disabledReason}
          data-testid={`toggle-call-summary-${call.call_sid || call.lead_id}`}
          className={`mt-3 flex items-center gap-1.5 text-[11px] uppercase tracking-wider transition-colors ${
            canExpand
              ? "text-[#C5A059] hover:text-[#E5C585]"
              : "text-[#525252] cursor-not-allowed opacity-60"
          }`}
        >
          <Bot className="w-3.5 h-3.5" />
          AI Call Summary
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {expanded && (
          <div className="mt-2 p-3 rounded bg-[#C5A059]/10 border border-[#C5A059]/20">
            {loading ? (
              <div className="flex items-center gap-2 text-[#A3A3A3] text-sm">
                <Loader2 className="w-4 h-4 animate-spin text-[#C5A059]" />
                Summarising with GPT-4o…
              </div>
            ) : summary ? (
              <p className="text-sm text-white leading-relaxed">{summary}</p>
            ) : (
              <p className="text-sm text-[#A3A3A3]">Summary unavailable.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default CustomerDetailPage;
