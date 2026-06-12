import React, { useState, useEffect } from 'react';
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../../context/AuthContext';
import NotificationBell from './NotificationBell';
import {
  LayoutDashboard,
  Users,
  Megaphone,
  Settings,
  LogOut,
  Menu,
  X,
  Bell,
  ChevronRight,
  Sun,
  Moon,
  Phone,
  BarChart3,
  UserCircle,
  TrendingUp,
} from 'lucide-react';

const DashboardLayout = () => {
  const { user, logout, isAdmin } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode');
    return saved !== null ? JSON.parse(saved) : true;
  });

  const navItems = [
    ...(isAdmin
      ? [{ path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' }]
      : []),
    ...(isAdmin
      ? []
      : [{ path: '/my-dashboard', icon: UserCircle, label: 'My Dashboard' }]),
    { path: '/virtual-customer', icon: Users, label: 'Virtual Customer' },
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
      <main className="flex-1 lg:ml-64 min-w-0">
        {/* Top Bar */}
        <header className={`sticky top-0 z-30 ${darkMode ? 'bg-[#0A0A0A]/80' : 'bg-white/80'} backdrop-blur-xl border-b ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
          <div className="flex items-center justify-between px-4 lg:px-8 py-4 gap-2">
            {/* Mobile Menu Button */}
            <button
              onClick={() => setSidebarOpen(true)}
              className={`lg:hidden flex-shrink-0 ${darkMode ? 'text-[#A1A1AA] hover:text-white' : 'text-gray-400 hover:text-gray-600'}`}
              data-testid="open-sidebar-btn"
            >
              <Menu size={24} />
            </button>

            {/* Mobile page title */}
            <div className="lg:hidden flex-1 min-w-0">
              <span className={`text-sm font-medium capitalize truncate block ${darkMode ? 'text-[#C5A059]' : 'text-gray-800'}`}>
                {(location.pathname.split('/')[1] || 'dashboard').replace(/-/g, ' ')}
              </span>
            </div>

            {/* Breadcrumb */}
            <div className="hidden lg:flex items-center gap-2 text-sm flex-1">
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

              <NotificationBell darkMode={darkMode} />

              {/* User Avatar - Mobile */}
              <div className="lg:hidden w-8 h-8 rounded-full bg-[#C5A059] flex items-center justify-center text-black text-sm font-medium">
                {user?.full_name?.charAt(0) || 'R'}
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="p-4 lg:p-8 min-w-0">
          <Outlet />
        </div>
      </main>

    </div>
  );
};

export default DashboardLayout;
