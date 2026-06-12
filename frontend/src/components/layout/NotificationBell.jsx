import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell,
  Phone,
  Clock,
  Calendar,
  AlertTriangle,
  Megaphone,
} from "lucide-react";
import { toast } from "sonner";
import { notificationsAPI } from "../../lib/api";
import { isNotificationUnread, sanitizeNotificationText } from "../../lib/brandLabels";

const getNotificationIcon = (type) => {
  switch (type) {
    case "rnr_followup":
      return Phone;
    case "stale_followup":
    case "dormant_lead":
      return Clock;
    case "task_overdue":
    case "task_reminder":
      return Calendar;
    case "hot_lead":
    case "new_lead_assigned":
    case "lead_transferred":
      return AlertTriangle;
    case "ai_call_summary":
      return Bell;
    case "reminder":
      return Calendar;
    case "alert":
      return AlertTriangle;
    case "message":
      return Megaphone;
    default:
      return Bell;
  }
};

const getUrgencyColor = (notification) => {
  const sev = (notification.severity || "").toLowerCase();
  const urg = (notification.urgency || "").toLowerCase();
  if (sev === "high" || urg === "urgent") {
    return { bg: "bg-red-500/10", text: "text-red-500", label: "High" };
  }
  if (sev === "medium" || urg === "action_needed") {
    return { bg: "bg-yellow-500/10", text: "text-yellow-500", label: "Medium" };
  }
  return { bg: "bg-blue-500/10", text: "text-blue-500", label: "Low" };
};

const NotificationBell = ({ darkMode }) => {
  const navigate = useNavigate();
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);

  const fetchNotifications = useCallback(async () => {
    try {
      const response = await notificationsAPI.getAll();
      setNotifications(response.data || []);
      setFetchError(false);
    } catch (error) {
      console.error("Failed to fetch notifications:", error);
      setFetchError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  const handleMarkAllRead = async () => {
    try {
      await notificationsAPI.markAllRead();
      await fetchNotifications();
      toast.success("All notifications marked as read");
    } catch (error) {
      console.error("Failed to mark all read:", error);
      toast.error("Could not mark all as read");
    }
  };

  const handleMarkRead = async (id) => {
    try {
      await notificationsAPI.markRead(id);
      if (String(id).startsWith("auto-")) {
        setNotifications((prev) => prev.filter((n) => n.id !== id));
      } else {
        setNotifications((prev) =>
          prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
        );
      }
    } catch (error) {
      console.error("Failed to mark notification read:", error);
      toast.error("Could not update notification");
    }
  };

  const unreadCount = notifications.filter(isNotificationUnread).length;

  return (
    <>
      <div className="relative">
        <button
          onClick={() => setShowNotifications(!showNotifications)}
          className={`relative p-2 rounded-lg transition-colors ${
            darkMode
              ? "text-[#A1A1AA] hover:text-white hover:bg-white/10"
              : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          }`}
          data-testid="notifications-btn"
        >
          <Bell size={20} strokeWidth={1.5} />
          {unreadCount > 0 && (
            <span className="absolute top-0 right-0 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>

        <AnimatePresence>
          {showNotifications && (
            <motion.div
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              className={`absolute right-0 mt-2 w-80 ${
                darkMode ? "bg-[#1A1A1A] border-white/10" : "bg-white border-gray-200"
              } border rounded-lg shadow-xl overflow-hidden z-50`}
              data-testid="notifications-panel"
            >
              <div
                className={`px-4 py-3 border-b ${
                  darkMode ? "border-white/10" : "border-gray-200"
                } flex items-center justify-between`}
              >
                <div>
                  <h3 className={`font-medium ${darkMode ? "text-white" : "text-gray-900"}`}>
                    Notifications
                  </h3>
                  <p className={`text-xs ${darkMode ? "text-[#52525B]" : "text-gray-500"}`}>
                    {unreadCount} unread
                  </p>
                </div>
                {unreadCount > 0 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleMarkAllRead();
                    }}
                    className="text-[#C5A059] text-xs hover:underline"
                    data-testid="mark-all-read-btn"
                  >
                    Mark all read
                  </button>
                )}
              </div>

              <div className="max-h-96 overflow-y-auto">
                {loading && notifications.length === 0 ? (
                  <div className="p-4 space-y-2">
                    {[1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className={`h-14 rounded-lg animate-pulse ${darkMode ? "bg-white/5" : "bg-gray-100"}`}
                      />
                    ))}
                  </div>
                ) : fetchError && notifications.length === 0 ? (
                  <div className="p-8 text-center">
                    <p className={`text-sm ${darkMode ? "text-red-400" : "text-red-600"}`}>
                      Couldn&apos;t load notifications
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setLoading(true);
                        fetchNotifications();
                      }}
                      className="text-[#C5A059] text-xs mt-2 hover:underline"
                    >
                      Retry
                    </button>
                  </div>
                ) : notifications.length === 0 ? (
                  <div className="p-8 text-center">
                    <Bell
                      className={`mx-auto ${darkMode ? "text-[#52525B]" : "text-gray-300"}`}
                      size={32}
                    />
                    <p className={`mt-2 text-sm ${darkMode ? "text-[#52525B]" : "text-gray-500"}`}>
                      No pending notifications
                    </p>
                  </div>
                ) : (
                  notifications.slice(0, 20).map((notification, idx) => {
                    const IconComponent = getNotificationIcon(notification.type);
                    const urgency = getUrgencyColor(notification);
                    return (
                      <div
                        key={notification.id || idx}
                        onClick={() => {
                          handleMarkRead(notification.id);
                          if (notification.lead_id) {
                            setShowNotifications(false);
                            navigate(`/customer/${notification.lead_id}`);
                          }
                        }}
                        className={`px-4 py-3 border-b ${
                          darkMode
                            ? "border-white/5 hover:bg-white/5"
                            : "border-gray-100 hover:bg-gray-50"
                        } cursor-pointer transition-colors ${
                          isNotificationUnread(notification)
                            ? darkMode
                              ? "bg-white/[0.02]"
                              : "bg-blue-50/50"
                            : ""
                        }`}
                        data-testid={`notification-${idx}`}
                      >
                        <div className="flex items-start gap-3">
                          <div
                            className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${urgency.bg} ${urgency.text}`}
                          >
                            <IconComponent size={14} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p
                                className={`text-sm font-medium truncate ${
                                  darkMode ? "text-white" : "text-gray-900"
                                }`}
                              >
                                {sanitizeNotificationText(notification.title || notification.lead_name)}
                              </p>
                              {isNotificationUnread(notification) && (
                                <span className="w-2 h-2 rounded-full bg-[#C5A059] flex-shrink-0" />
                              )}
                            </div>
                            <p
                              className={`text-xs ${
                                darkMode ? "text-[#A1A1AA]" : "text-gray-600"
                              } mt-0.5 line-clamp-2`}
                            >
                              {sanitizeNotificationText(notification.message)}
                            </p>
                            <span
                              className={`text-[10px] ${urgency.text} mt-1 block uppercase tracking-wider`}
                            >
                              {urgency.label}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <div
                className={`px-4 py-2 border-t ${
                  darkMode ? "border-white/10" : "border-gray-200"
                }`}
              >
                <button
                  type="button"
                  onClick={() => {
                    setShowNotifications(false);
                    navigate("/notifications");
                  }}
                  className="text-[#C5A059] text-sm hover:underline w-full text-center"
                >
                  View All Alerts
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {showNotifications && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setShowNotifications(false)}
        />
      )}
    </>
  );
};

export default NotificationBell;
