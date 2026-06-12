import React, { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Bell, ArrowLeft, AlertTriangle, Phone, Calendar, Clock, Sparkles } from "lucide-react";
import { notificationsAPI } from "../lib/api";
import { isNotificationUnread, sanitizeNotificationText } from "../lib/brandLabels";
import { Button } from "../components/ui/button";
import { toast } from "sonner";

const severityStyle = (n) => {
  const sev = (n.severity || "").toLowerCase();
  const urg = (n.urgency || "").toLowerCase();
  if (sev === "high" || urg === "urgent") {
    return { bg: "bg-red-500/10", text: "text-red-400", border: "border-red-500/30", label: "High" };
  }
  if (sev === "medium" || urg === "action_needed") {
    return { bg: "bg-yellow-500/10", text: "text-yellow-400", border: "border-yellow-500/30", label: "Medium" };
  }
  return { bg: "bg-blue-500/10", text: "text-blue-400", border: "border-blue-500/30", label: "Low" };
};

const iconFor = (type) => {
  if (type === "rnr_followup") return Phone;
  if (type === "stale_followup" || type === "dormant_lead") return Clock;
  if (type === "task_overdue" || type === "task_reminder" || type === "reminder") return Calendar;
  if (type === "ai_call_summary") return Sparkles;
  if (type === "hot_lead" || type === "new_lead_assigned" || type === "lead_transferred") return AlertTriangle;
  return Clock;
};

const dateLabel = (iso) => {
  if (!iso) return "Earlier";
  const d = new Date(iso);
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startItem = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = (startToday - startItem) / 86400000;
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" });
};

const NotificationsPage = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  const load = async () => {
    if (!hasLoadedOnce) setLoading(true);
    try {
      const { data } = await notificationsAPI.getAll();
      setItems(data || []);
      setHasLoadedOnce(true);
    } catch {
      toast.error("Failed to load notifications");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const grouped = useMemo(() => {
    const map = {};
    for (const n of items) {
      const key = dateLabel(n.created_at);
      if (!map[key]) map[key] = [];
      map[key].push(n);
    }
    return Object.entries(map);
  }, [items]);

  const markAll = async () => {
    try {
      await notificationsAPI.markAllRead();
      await load();
      toast.success("All alerts cleared");
    } catch {
      toast.error("Could not mark all as read");
    }
  };

  const markOne = async (id) => {
    try {
      await notificationsAPI.markRead(id);
      if (String(id).startsWith("auto-")) {
        setItems((prev) => prev.filter((n) => n.id !== id));
      } else {
        setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      }
    } catch {
      toast.error("Could not update notification");
    }
  };

  return (
    <motion.div className="space-y-6 max-w-3xl mx-auto">
      <motion.div className="flex items-center justify-between gap-4">
        <motion.div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-[#A1A1AA]">
            <ArrowLeft size={18} />
          </Button>
          <motion.div>
            <h1 className="font-serif text-2xl text-white flex items-center gap-2">
              <Bell className="text-[#C5A059]" size={24} />
              Notifications
            </h1>
            <p className="text-[#52525B] text-sm mt-1">System alerts grouped by date</p>
          </motion.div>
        </motion.div>
        {items.some(isNotificationUnread) && (
          <Button size="sm" variant="outline" onClick={markAll} className="border-[#C5A059]/40 text-[#C5A059]">
            Mark all read
          </Button>
        )}
      </motion.div>

      {loading && !hasLoadedOnce ? (
        <motion.div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <motion.div key={i} className="glass-card rounded-lg p-4 animate-pulse h-20 bg-white/5" />
          ))}
        </motion.div>
      ) : items.length === 0 ? (
        <motion.div className="glass-card rounded-lg p-12 text-center text-[#52525B]">No notifications</motion.div>
      ) : (
        <motion.div className="space-y-8">
          {grouped.map(([day, dayItems]) => (
            <motion.div key={day}>
              <h2 className="text-[#C5A059] text-xs uppercase tracking-widest mb-3">{day}</h2>
              <motion.div className="space-y-2">
                {dayItems.map((n) => {
                  const Icon = iconFor(n.type);
                  const style = severityStyle(n);
                  return (
                    <motion.div
                      key={n.id}
                      layout
                      className={`glass-card rounded-lg p-4 flex gap-3 cursor-pointer border ${
                        isNotificationUnread(n) ? `${style.border} ${style.bg}` : "border-white/5"
                      }`}
                      onClick={() => {
                        markOne(n.id);
                        if (n.lead_id) navigate(`/customer/${n.lead_id}`);
                      }}
                    >
                      <motion.div
                        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${style.bg}`}
                      >
                        <Icon size={18} className={style.text} />
                      </motion.div>
                      <motion.div className="flex-1 min-w-0">
                        <motion.div className="flex items-center gap-2">
                          <p className="text-white font-medium text-sm">
                            {sanitizeNotificationText(n.title || n.lead_name)}
                          </p>
                          <span className={`text-[10px] uppercase ${style.text}`}>{style.label}</span>
                        </motion.div>
                        <p className="text-[#A1A1AA] text-xs mt-1">{sanitizeNotificationText(n.message)}</p>
                        {n.is_auto && (
                          <span className="text-[10px] text-[#52525B] mt-2 inline-block">Auto alert</span>
                        )}
                      </motion.div>
                      {isNotificationUnread(n) && (
                        <span className="w-2 h-2 rounded-full bg-[#C5A059] flex-shrink-0 mt-2" />
                      )}
                    </motion.div>
                  );
                })}
              </motion.div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
};

export default NotificationsPage;
