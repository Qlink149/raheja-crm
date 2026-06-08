import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../../context/AuthContext';
import { notificationsAPI } from '../../lib/api';
import {
  LayoutDashboard,
  Megaphone,
  Settings,
  LogOut,
  Menu,
  X,
  Bell,
  ChevronRight,
  Sun,
  Moon,
  Clock,
  AlertTriangle,
  Phone,
  Calendar,
  BarChart3,
  FileCode,
  UserCircle,
  TrendingUp,
  FileText
} from 'lucide-react';

const DashboardLayout = () => {
  const { user, logout, isAdmin } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode');
    return saved !== null ? JSON.parse(saved) : true;
  });
  const [notifications, setNotifications] = useState([]);

  const navItems = [
    ...(isAdmin
      ? [{ path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' }]
      : []),
    ...(isAdmin
      ? []
      : [{ path: '/my-dashboard', icon: UserCircle, label: 'My Dashboard' }]),
    { path: '/ai-calling', icon: Phone, label: 'AI Calling' },
    ...(isAdmin
      ? [
          { path: '/campaigns', icon: Megaphone, label: 'Campaigns' },
          { path: '/sales-dashboard', icon: BarChart3, label: 'Sales Dashboard' },
          { path: '/marketing-dashboard', icon: TrendingUp, label: 'Marketing' },
        ]
      : []),
    { path: '/notifications', icon: Bell, label: 'Notifications' },
    ...(isAdmin ? [{ path: '/settings', icon: Settings, label: 'Settings' }] : []),
  ];

  const fetchNotifications = useCallback(async () => {
    try {
      const response = await notificationsAPI.getAll();
      setNotifications(response.data || []);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  useEffect(() => {
    localStorage.setItem('darkMode', JSON.stringify(darkMode));
    // Apply theme to document
    if (darkMode) {
      document.documentElement.classList.remove('light-mode');
      document.documentElement.classList.add('dark-mode');
    } else {
      document.documentElement.classList.remove('dark-mode');
      document.documentElement.classList.add('light-mode');
    }
  }, [darkMode]);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationsAPI.markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      await fetchNotifications();
    } catch (error) {
      console.error('Failed to mark all read:', error);
    }
  };

  const handleMarkRead = async (id) => {
    try {
      await notificationsAPI.markRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch (error) {
      console.error('Failed to mark notification read:', error);
    }
  };

  const getNotificationIcon = (type) => {
    switch (type) {
      case 'rnr_followup':
        return Phone;
      case 'stale_followup':
      case 'dormant_lead':
        return Clock;
      case 'task_overdue':
      case 'task_reminder':
        return Calendar;
      case 'hot_vip_lead':
      case 'new_lead_assigned':
      case 'lead_transferred':
        return AlertTriangle;
      case 'ai_call_summary':
        return Bell;
      case 'reminder':
        return Calendar;
      case 'alert':
        return AlertTriangle;
      case 'message':
        return Megaphone;
      default:
        return Bell;
    }
  };

  const getUrgencyColor = (notification) => {
    const sev = (notification.severity || '').toLowerCase();
    const urg = (notification.urgency || '').toLowerCase();
    if (sev === 'high' || urg === 'urgent') {
      return { bg: 'bg-red-500/10', text: 'text-red-500', label: 'High' };
    }
    if (sev === 'medium' || urg === 'action_needed') {
      return { bg: 'bg-yellow-500/10', text: 'text-yellow-500', label: 'Medium' };
    }
    return { bg: 'bg-blue-500/10', text: 'text-blue-500', label: 'Low' };
  };

  const unreadCount = notifications.filter(n => !n.is_read).length;

  return (
    <div className={`min-h-screen flex ${darkMode ? 'bg-[#0A0A0A]' : 'bg-gray-100'}`}>
      {/* Sidebar - Desktop */}
      <aside className={`hidden lg:flex flex-col w-64 ${darkMode ? 'bg-[#0A0A0A] border-white/10' : 'bg-white border-gray-200'} border-r fixed h-full`}>
        {/* Logo */}
        <div className={`p-6 border-b ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
          <img
            src="https://customer-assets.emergentagent.com/job_rustomjee-sales-hub/artifacts/qap04r7n_Rustomjee_logo-removebg-preview.png"
            alt="Rustomjee"
            className={`h-8 invert ${!darkMode ? "" : ""}`}
            data-testid="sidebar-logo"
          />
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-6">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-6 py-3 text-sm transition-all ${
                  isActive
                    ? 'text-[#C5A059] bg-[#C5A059]/10 border-r-2 border-[#C5A059]'
                    : darkMode 
                      ? 'text-[#A1A1AA] hover:text-white hover:bg-white/5'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                }`
              }
              data-testid={`nav-${item.label.toLowerCase().replace(' ', '-')}`}
            >
              <item.icon size={20} strokeWidth={1.5} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User Section */}
        <div className={`p-4 border-t ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
          <div className="flex items-center gap-3 px-2 py-3">
            <div className="w-10 h-10 rounded-full bg-[#C5A059] flex items-center justify-center text-black font-medium">
              {user?.full_name?.charAt(0) || 'R'}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm truncate ${darkMode ? 'text-white' : 'text-gray-900'}`}>{user?.full_name || 'Roshini'}</p>
              <p className={`text-xs truncate ${darkMode ? 'text-[#52525B]' : 'text-gray-500'}`}>{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className={`w-full flex items-center gap-3 px-4 py-2 text-sm ${darkMode ? 'text-[#A1A1AA]' : 'text-gray-600'} hover:text-red-500 transition-colors mt-2`}
            data-testid="logout-btn"
          >
            <LogOut size={18} strokeWidth={1.5} />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Mobile Sidebar */}
      <motion.aside
        className={`lg:hidden fixed inset-y-0 left-0 z-50 w-64 ${darkMode ? 'bg-[#0A0A0A] border-white/10' : 'bg-white border-gray-200'} border-r ${
          sidebarOpen ? 'block' : 'hidden'
        }`}
        initial={{ x: -256 }}
        animate={{ x: sidebarOpen ? 0 : -256 }}
        transition={{ duration: 0.2 }}
      >
        {/* Close Button */}
        <button
          onClick={() => setSidebarOpen(false)}
          className={`absolute top-4 right-4 ${darkMode ? 'text-[#A1A1AA] hover:text-white' : 'text-gray-400 hover:text-gray-600'}`}
          data-testid="close-sidebar-btn"
        >
          <X size={24} />
        </button>

        {/* Logo */}
        <div className={`p-6 border-b ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
          <img
            src="https://customer-assets.emergentagent.com/job_rustomjee-sales-hub/artifacts/qap04r7n_Rustomjee_logo-removebg-preview.png"
            alt="Rustomjee"
            className={`h-8 invert ${!darkMode ? "" : ""}`}
          />
        </div>

        {/* Navigation */}
        <nav className="py-6">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-6 py-3 text-sm transition-all ${
                  isActive
                    ? 'text-[#C5A059] bg-[#C5A059]/10 border-r-2 border-[#C5A059]'
                    : darkMode 
                      ? 'text-[#A1A1AA] hover:text-white hover:bg-white/5'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                }`
              }
            >
              <item.icon size={20} strokeWidth={1.5} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User Section */}
        <div className={`absolute bottom-0 left-0 right-0 p-4 border-t ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
          <button
            onClick={handleLogout}
            className={`w-full flex items-center gap-3 px-4 py-2 text-sm ${darkMode ? 'text-[#A1A1AA]' : 'text-gray-600'} hover:text-red-500 transition-colors`}
          >
            <LogOut size={18} strokeWidth={1.5} />
            Sign Out
          </button>
        </div>
      </motion.aside>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="flex-1 lg:ml-64">
        {/* Top Bar */}
        <header className={`sticky top-0 z-30 ${darkMode ? 'bg-[#0A0A0A]/80' : 'bg-white/80'} backdrop-blur-xl border-b ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
          <div className="flex items-center justify-between px-4 lg:px-8 py-4">
            {/* Mobile Menu Button */}
            <button
              onClick={() => setSidebarOpen(true)}
              className={`lg:hidden ${darkMode ? 'text-[#A1A1AA] hover:text-white' : 'text-gray-400 hover:text-gray-600'}`}
              data-testid="open-sidebar-btn"
            >
              <Menu size={24} />
            </button>

            {/* Breadcrumb */}
            <div className="hidden lg:flex items-center gap-2 text-sm">
              <span className={darkMode ? 'text-[#52525B]' : 'text-gray-400'}>Home</span>
              <ChevronRight size={14} className={darkMode ? 'text-[#52525B]' : 'text-gray-400'} />
              <span className="text-[#C5A059] capitalize">
                {location.pathname.split('/')[1] || 'Dashboard'}
              </span>
            </div>

            {/* Right Section */}
            <div className="flex items-center gap-4">
              {/* Dark/Light Mode Toggle */}
              <button
                onClick={toggleDarkMode}
                className={`p-2 rounded-lg transition-colors ${darkMode ? 'text-[#A1A1AA] hover:text-white hover:bg-white/10' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'}`}
                data-testid="theme-toggle-btn"
                title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
              >
                {darkMode ? <Sun size={20} strokeWidth={1.5} /> : <Moon size={20} strokeWidth={1.5} />}
              </button>

              {/* Notifications */}
              <div className="relative">
                <button
                  onClick={() => setShowNotifications(!showNotifications)}
                  className={`relative p-2 rounded-lg transition-colors ${darkMode ? 'text-[#A1A1AA] hover:text-white hover:bg-white/10' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'}`}
                  data-testid="notifications-btn"
                >
                  <Bell size={20} strokeWidth={1.5} />
                  {unreadCount > 0 && (
                    <span className="absolute top-0 right-0 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </button>

                {/* Notifications Panel */}
                <AnimatePresence>
                  {showNotifications && (
                    <motion.div
                      initial={{ opacity: 0, y: 10, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 10, scale: 0.95 }}
                      className={`absolute right-0 mt-2 w-80 ${darkMode ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-gray-200'} border rounded-lg shadow-xl overflow-hidden z-50`}
                      data-testid="notifications-panel"
                    >
                      <div className={`px-4 py-3 border-b ${darkMode ? 'border-white/10' : 'border-gray-200'} flex items-center justify-between`}>
                        <div>
                          <h3 className={`font-medium ${darkMode ? 'text-white' : 'text-gray-900'}`}>Notifications</h3>
                          <p className={`text-xs ${darkMode ? 'text-[#52525B]' : 'text-gray-500'}`}>
                            {unreadCount} unread
                          </p>
                        </div>
                        {unreadCount > 0 && (
                          <button onClick={(e) => { e.stopPropagation(); handleMarkAllRead(); }} className="text-[#C5A059] text-xs hover:underline" data-testid="mark-all-read-btn">
                            Mark all read
                          </button>
                        )}
                      </div>
                      
                      <div className="max-h-96 overflow-y-auto">
                        {notifications.length === 0 ? (
                          <div className="p-8 text-center">
                            <Bell className={`mx-auto ${darkMode ? 'text-[#52525B]' : 'text-gray-300'}`} size={32} />
                            <p className={`mt-2 text-sm ${darkMode ? 'text-[#52525B]' : 'text-gray-500'}`}>
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
                                className={`px-4 py-3 border-b ${darkMode ? 'border-white/5 hover:bg-white/5' : 'border-gray-100 hover:bg-gray-50'} cursor-pointer transition-colors ${!notification.is_read ? (darkMode ? 'bg-white/[0.02]' : 'bg-blue-50/50') : ''}`}
                                data-testid={`notification-${idx}`}
                              >
                                <div className="flex items-start gap-3">
                                  <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${urgency.bg} ${urgency.text}`}>
                                    <IconComponent size={14} />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <p className={`text-sm font-medium truncate ${darkMode ? 'text-white' : 'text-gray-900'}`}>
                                        {notification.title || notification.lead_name}
                                      </p>
                                      {!notification.is_read && <span className="w-2 h-2 rounded-full bg-[#C5A059] flex-shrink-0" />}
                                    </div>
                                    <p className={`text-xs ${darkMode ? 'text-[#A1A1AA]' : 'text-gray-600'} mt-0.5 line-clamp-2`}>
                                      {notification.message}
                                    </p>
                                    <span className={`text-[10px] ${urgency.text} mt-1 block uppercase tracking-wider`}>
                                      {urgency.label}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>

                      <div className={`px-4 py-2 border-t ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
                        <button
                          type="button"
                          onClick={() => {
                            setShowNotifications(false);
                            navigate('/notifications');
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

              {/* User Avatar - Mobile */}
              <div className="lg:hidden w-8 h-8 rounded-full bg-[#C5A059] flex items-center justify-center text-black text-sm font-medium">
                {user?.full_name?.charAt(0) || 'R'}
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="p-4 lg:p-8">
          <Outlet />
        </div>
      </main>

      {/* Close notifications when clicking outside */}
      {showNotifications && (
        <div 
          className="fixed inset-0 z-40" 
          onClick={() => setShowNotifications(false)}
        />
      )}
    </div>
  );
};

export default DashboardLayout;
