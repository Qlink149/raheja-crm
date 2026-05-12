import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Home,
  Users,
  Settings,
  LogOut,
  Building2,
  Megaphone,
  PhoneCall,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../components/ui/tooltip";

const Sidebar = ({ activePage, onLogout, currentUser }) => {
  const navigate = useNavigate();
  const name = currentUser?.name || "Ravinder";
  const initials = currentUser?.initials || (name.charAt(0) || "R").toUpperCase();

  const navItems = [
    { id: "dashboard", icon: Home, label: "Dashboard", path: "/dashboard" },
    { id: "virtual-customer", icon: Users, label: "Virtual Customer", path: "/virtual-customer" },
    { id: "ai-calling", icon: PhoneCall, label: "AI Calling", path: "/ai-calling" },
    { id: "campaigns", icon: Megaphone, label: "Campaigns", path: "/campaigns" },
    { id: "settings", icon: Settings, label: "Settings", path: "/settings" },
  ];

  return (
    <TooltipProvider>
      <motion.aside
        initial={{ x: -20, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="fixed left-0 top-0 h-screen w-20 lg:w-64 bg-[#0A0A0A] border-r border-white/10 flex flex-col z-50"
      >
        {/* Logo */}
        <div className="p-6 border-b border-white/10">
          <div className="flex items-center gap-3">
            <img
              src="https://customer-assets.emergentagent.com/job_rustomjee-sales-hub/artifacts/qap04r7n_Rustomjee_logo-removebg-preview.png"
              alt="Rustomjee"
              className="h-8 w-auto invert"
            />
            <div className="hidden lg:block">
              <p className="kicker">Sales Hub</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <div className="space-y-1.5">
            {navItems.map((item) => {
              const isActive = activePage === item.id;
              return (
                <Tooltip key={item.id} delayDuration={0}>
                  <TooltipTrigger asChild>
                    <button
                      data-testid={`nav-${item.id}`}
                      onClick={() => navigate(item.path)}
                      className={`relative w-full flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-300 ease-premium btn-tactile ${
                        isActive
                          ? "bg-[#C5A059]/15 text-[#C5A059] shadow-[0_0_20px_-8px_rgba(197,160,89,0.4)]"
                          : "text-[#A3A3A3] hover:bg-white/5 hover:text-white"
                      }`}
                    >
                      {/* Active gold accent bar */}
                      {isActive && (
                        <motion.span
                          layoutId="sidebar-active-bar"
                          className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-gradient-to-b from-[#E5C585] via-[#C5A059] to-[#8A6D3B]"
                          transition={{ type: "spring", stiffness: 380, damping: 30 }}
                        />
                      )}
                      <item.icon className="w-5 h-5 flex-shrink-0" strokeWidth={1.5} />
                      <span className="hidden lg:block text-sm font-medium tracking-tight">
                        {item.label}
                      </span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="lg:hidden bg-[#1A1A1A] border-white/10 text-white">
                    {item.label}
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </nav>

        {/* User Section */}
        <div className="p-4 border-t border-white/10">
          <div className="flex items-center gap-3 px-4 py-3 mb-2">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#C5A059] to-[#8A6D3B] flex items-center justify-center text-black font-semibold text-sm shadow-[0_0_16px_-6px_rgba(197,160,89,0.5)]">
              {initials}
            </div>
            <div className="hidden lg:block min-w-0">
              <p data-testid="sidebar-user-name" className="text-white text-sm font-medium truncate">
                {name}
              </p>
              <p className="text-[10px] text-[#525252] uppercase tracking-widest">Operator</p>
            </div>
          </div>

          <Tooltip delayDuration={0}>
            <TooltipTrigger asChild>
              <button
                data-testid="logout-btn"
                onClick={onLogout}
                className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-red-400/70 hover:bg-red-900/20 hover:text-red-400 transition-all duration-300 ease-premium btn-tactile"
              >
                <LogOut className="w-5 h-5" strokeWidth={1.5} />
                <span className="hidden lg:block text-sm font-medium">Logout</span>
              </button>
            </TooltipTrigger>
            <TooltipContent side="right" className="lg:hidden bg-[#1A1A1A] border-white/10 text-white">
              Logout
            </TooltipContent>
          </Tooltip>
        </div>
      </motion.aside>
    </TooltipProvider>
  );
};

export default Sidebar;
