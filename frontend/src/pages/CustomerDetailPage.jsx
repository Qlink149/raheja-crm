import { useState, useEffect, useMemo } from "react";
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
  FileText,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { ScrollArea } from "../components/ui/scroll-area";
import Sidebar from "../components/Sidebar";
import EmptyState from "../components/feedback/EmptyState";
import { CustomerDetailSkeleton } from "../components/feedback/Skeletons";
import { api } from "../lib/api";

const CustomerDetailPage = ({ onLogout, currentUser }) => {
  const navigate = useNavigate();
  const { id } = useParams();
  const [lead, setLead] = useState(null);
  const [loading, setLoading] = useState(true);
  const [earliestCallMs, setEarliestCallMs] = useState(null);

  useEffect(() => {
    fetchLeadDetail();
  }, [id]);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    (async () => {
      try {
        const res = await api.get(`/leads/${id}/calls`);
        if (!mounted) return;
        const list = res.data?.calls || [];
        let minTs = null;
        for (const c of list) {
          const raw = c.created_at || c.call_date;
          if (!raw) continue;
          const t = new Date(raw).getTime();
          if (!Number.isNaN(t) && (minTs === null || t < minTs)) minTs = t;
        }
        setEarliestCallMs(minTs);
      } catch {
        if (mounted) setEarliestCallMs(null);
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

  const formatTimelineDate = (ms) => {
    if (ms == null || Number.isNaN(ms)) return "—";
    return new Date(ms).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    });
  };

  // Generate context updates based on lead data; Initial contact uses earliest call_history created_at
  const generateContextUpdates = (leadRow, earliestMs) => {
    const updates = [];
    const baseDate = new Date();
    
    // Add updates based on available lead data - only if value exists and is not empty
    if (leadRow?.configuration && leadRow.configuration !== '' && leadRow.configuration !== 'N/A') {
      updates.push({
        date: new Date(baseDate.getTime() - 30 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' }),
        icon: 'phone',
        context: `User interested in ${leadRow.configuration} configuration`,
        type: 'call'
      });
    }
    
    if (leadRow?.current_residence_type && leadRow.current_residence_type !== '' && leadRow.current_residence_type !== 'N/A') {
      updates.push({
        date: new Date(baseDate.getTime() - 25 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' }),
        icon: 'whatsapp',
        context: `Currently residing in ${leadRow.current_residence_type}`,
        type: 'whatsapp'
      });
    }
    
    if (leadRow?.reason_for_purchase && leadRow.reason_for_purchase !== '' && leadRow.reason_for_purchase !== 'N/A') {
      updates.push({
        date: new Date(baseDate.getTime() - 20 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' }),
        icon: 'human',
        context: `Purchase intent: ${leadRow.reason_for_purchase}`,
        type: 'human'
      });
    }
    
    if (leadRow?.possession_requirement && leadRow.possession_requirement !== '' && leadRow.possession_requirement !== 'N/A') {
      updates.push({
        date: new Date(baseDate.getTime() - 15 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' }),
        icon: 'phone',
        context: `Possession preference: ${leadRow.possession_requirement}`,
        type: 'call'
      });
    }
    
    if (leadRow?.budget && leadRow.budget !== '' && leadRow.budget !== '0' && leadRow.budget !== 'N/A') {
      updates.push({
        date: new Date(baseDate.getTime() - 10 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' }),
        icon: 'whatsapp',
        context: `Budget confirmed: ${leadRow.budget} Cr`,
        type: 'whatsapp'
      });
    }
    
    if (leadRow?.project && leadRow.project !== '' && leadRow.project !== 'N/A') {
      updates.push({
        date: new Date(baseDate.getTime() - 5 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' }),
        icon: 'human',
        context: `Showed interest in ${leadRow.project}`,
        type: 'human'
      });
    }
    
    if (leadRow?.next_action_date && leadRow.next_action_date !== '' && leadRow.next_action_date !== 'N/A') {
      updates.push({
        date: new Date(baseDate.getTime() - 2 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' }),
        icon: 'human',
        context: `Site visit scheduled for ${leadRow.next_action_date}`,
        type: 'human'
      });
    }

    if (earliestMs != null && !Number.isNaN(earliestMs)) {
      updates.unshift({
        date: formatTimelineDate(earliestMs),
        icon: "phone",
        context: "Initial contact made",
        type: "call",
      });
    }

    if (updates.length > 0) return updates;
    return [
      {
        date: "—",
        icon: "phone",
        context: "Initial contact made",
        type: "call",
      },
    ];
  };

  const contextUpdates = useMemo(
    () => (lead ? generateContextUpdates(lead, earliestCallMs) : []),
    [lead, earliestCallMs]
  );

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

  if (loading) {
    return (
      <div className="flex min-h-screen bg-[#0A0A0A]">
        <Sidebar activePage="virtual-customer" onLogout={onLogout} currentUser={currentUser} />
        <main className="flex-1 ml-20 lg:ml-64 p-6 overflow-auto">
          <div className="max-w-7xl mx-auto">
            <CustomerDetailSkeleton />
          </div>
        </main>
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="flex min-h-screen bg-[#0A0A0A]">
        <Sidebar activePage="virtual-customer" onLogout={onLogout} currentUser={currentUser} />
        <main className="flex-1 ml-20 lg:ml-64 flex items-center justify-center p-8">
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
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#0A0A0A]">
      <Sidebar activePage="virtual-customer" onLogout={onLogout} currentUser={currentUser} />

      <main className="flex-1 ml-20 lg:ml-64 p-6 overflow-auto">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="max-w-7xl mx-auto"
        >
          {/* Back Button */}
          <motion.button
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            onClick={() => navigate("/virtual-customer")}
            className="flex items-center gap-2 text-[#A3A3A3] hover:text-[#C5A059] mb-6 transition-colors"
            data-testid="back-to-customers-btn"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Customers</span>
          </motion.button>

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
                {lead.vip_category && (
                  <span className="flex items-center gap-1 px-3 py-1 bg-[#C5A059]/20 text-[#C5A059] border border-[#C5A059]/30 rounded-sm text-sm">
                    <Crown className="w-4 h-4" />
                    VIP Client
                  </span>
                )}
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
                  </div>
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
                fallback={lead.transcript ? "" : "Transcript unavailable or insufficient data for analysis."}
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
                fallback={(lead.transcript || lead.project || lead.disposition) ? "" : "Insufficient data to generate a strategic recommendation."}
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
                    value={(() => {
                      const b = lead.budget;
                      if (
                        b != null &&
                        b !== "" &&
                        b !== "0" &&
                        b !== 0 &&
                        b !== "Profiling in Progress"
                      ) {
                        const s = String(b).trim();
                        if (/cr/i.test(s)) return s;
                        return `${s} Cr`;
                      }
                      const bc = (lead.budget_category || "").trim();
                      if (bc && bc !== "Other" && bc !== "Profiling in Progress") return bc;
                      return "";
                    })()}
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
                    value={lead.location_category}
                  />
                  <DataDNAItem
                    icon={Target}
                    label="Purpose"
                    value={lead.reason_for_purchase}
                  />
                </div>
              </div>
            </motion.div>

            {/* Interaction Timeline */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="lg:col-span-3 glass-card rounded-xl p-6 min-w-0 lg:max-h-[calc(100vh-180px)] flex flex-col"
            >
              <h2 className="kicker mb-6 flex-shrink-0">Interaction Timeline</h2>
              <div className="flex-1 min-h-0">
                <CallsTimeline leadId={id} />
              </div>
            </motion.div>

            {/* Context Update Timeline */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="lg:col-span-4 glass-card rounded-xl p-6 min-w-0 lg:max-h-[calc(100vh-180px)] flex flex-col"
            >
              <div className="flex items-center gap-2 mb-6 flex-shrink-0">
                <History className="w-5 h-5 text-[#C5A059]" />
                <h2 className="kicker">Context Updates</h2>
              </div>

              <ScrollArea className="flex-1 min-h-0 max-h-80 lg:max-h-none">
                <div className="relative pr-2">
                  {/* Timeline line */}
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
                        {/* Icon */}
                        <div className={`relative z-10 flex-shrink-0 w-9 h-9 rounded-full border flex items-center justify-center ${getContextIconBg(update.type)}`}>
                          {getContextIcon(update.type)}
                        </div>

                        {/* Content */}
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
          </div>
        </motion.div>
      </main>
    </div>
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
const CallsTimeline = ({ leadId }) => {
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await api.get(`/leads/${leadId}/calls`);
        if (mounted) setCalls(res.data?.calls || []);
      } catch (e) {
        console.error(e);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [leadId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[#A3A3A3] text-sm">
        <Loader2 className="w-4 h-4 animate-spin text-[#C5A059]" />
        Loading calls…
      </div>
    );
  }

  if (calls.length === 0) {
    return <p className="text-sm text-[#A3A3A3]">No call interactions yet for this customer.</p>;
  }

  return (
    <ScrollArea className="h-full max-h-[60vh] lg:max-h-none pr-2">
      <div className="space-y-4 pr-2">
        {calls.map((call) => (
          <CallCard key={call.call_sid || `${call.lead_id}-${call.call_date}`} call={call} />
        ))}
      </div>
    </ScrollArea>
  );
};

const formatCallDate = (raw) => {
  if (!raw) return "Unknown date";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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
  const aiWorthy = call.ai_worthy !== false;
  const [expanded, setExpanded] = useState(false);
  const [summary, setSummary] = useState(
    call.ai_call_summary || (aiWorthy ? "" : "No meaningful conversation")
  );
  const [loading, setLoading] = useState(false);

  const label = call.disposition || call.status || "Unknown";

  const toggle = async () => {
    if (!aiWorthy) return;
    const next = !expanded;
    setExpanded(next);
    if (next && !summary && !loading) {
      setLoading(true);
      try {
        const params = {};
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
    <div className="bg-white/5 rounded-lg border border-white/5 overflow-hidden">
      <div className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-xs text-[#A3A3A3]">
            <PhoneCall className="w-3.5 h-3.5 text-[#C5A059]" />
            <span>{formatCallDate(call.call_date)}</span>
          </div>
          <span className={`px-2 py-0.5 rounded text-[11px] border ${dispositionStyle(call.disposition, call.status)}`}>
            {label}
          </span>
        </div>

        {/* Audio player */}
        {call.recording_url ? (
          <audio
            controls
            src={call.recording_url}
            className="w-full audio-gold"
            data-testid={`call-audio-${call.lead_id}`}
          />
        ) : (
          <p className="text-xs text-[#525252] italic">Recording unavailable.</p>
        )}

        {/* AI Summary toggle */}
        <button
          type="button"
          onClick={toggle}
          disabled={!aiWorthy}
          title={!aiWorthy ? "No meaningful conversation — AI summary disabled" : undefined}
          data-testid={`toggle-call-summary-${call.call_sid || call.lead_id}`}
          className={`mt-3 flex items-center gap-1.5 text-[11px] uppercase tracking-wider transition-colors ${
            aiWorthy
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
