import { motion } from "framer-motion";
import {
  Settings,
  UserCircle,
  Bell,
  Users,
  KeyRound,
  Shield,
  Sparkles,
} from "lucide-react";
const COMING_SOON = [
  {
    icon: UserCircle,
    title: "Profile",
    description: "Update your name, avatar, and contact details.",
  },
  {
    icon: Bell,
    title: "Notifications",
    description: "Choose which calls, leads, and campaign events ping you.",
  },
  {
    icon: Users,
    title: "Team Access",
    description: "Invite teammates and tune role-based permissions.",
  },
  {
    icon: KeyRound,
    title: "API Keys",
    description: "Generate platform tokens for integrations.",
  },
  {
    icon: Shield,
    title: "Security",
    description: "Password rotation, SSO, and active session control.",
  },
  {
    icon: Sparkles,
    title: "Workspace Theme",
    description: "Personalize accents, density, and typography.",
  },
];

const SettingsPage = () => {
  return (
    <motion.div className="space-y-8">

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="max-w-6xl mx-auto"
        >
          {/* Hero */}
          <div className="relative overflow-hidden rounded-2xl glass-card p-10 mb-10">
            {/* Decorative gold orbits */}
            <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-[#C5A059]/10 blur-3xl" />
            <div className="absolute -bottom-16 -left-16 w-56 h-56 rounded-full bg-[#C5A059]/5 blur-3xl" />

            <div className="relative flex flex-col md:flex-row md:items-center gap-6">
              <div className="relative flex-shrink-0">
                <div className="absolute inset-0 -m-2 rounded-full border border-[#C5A059]/15" />
                <div className="absolute inset-0 -m-5 rounded-full border border-[#C5A059]/8" />
                <div className="relative flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-[#C5A059]/25 to-[#8A6D3B]/15 border border-[#C5A059]/40 shadow-[0_0_36px_-6px_rgba(197,160,89,0.4)]">
                  <Settings className="w-9 h-9 text-[#C5A059]" strokeWidth={1.4} />
                </div>
              </div>

              <div className="min-w-0">
                <p className="kicker mb-3">Workspace</p>
                <h1 className="page-title text-4xl tracking-tight mb-2">
                  Settings
                </h1>
                <p className="page-subtitle max-w-2xl">
                  A unified control room for your profile, notifications, team
                  access, and integrations is on the way. We&apos;re keeping the
                  surface minimal until each setting is wired to a real,
                  testable backend.
                </p>
                <span className="inline-flex items-center gap-2 mt-4 px-3 py-1.5 rounded-full bg-[#C5A059]/15 border border-[#C5A059]/30 text-[#C5A059] text-xs font-medium uppercase tracking-widest">
                  <Sparkles className="w-3.5 h-3.5" />
                  Coming Soon
                </span>
              </div>
            </div>
          </div>

          {/* Feature placeholders */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {COMING_SOON.map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.4,
                  delay: 0.05 + i * 0.04,
                  ease: [0.22, 1, 0.36, 1],
                }}
                className="relative glass-card rounded-xl p-6 opacity-80 hover:opacity-100 transition-opacity duration-300"
              >
                <div className="flex items-start gap-4">
                  <div className="p-2.5 rounded-lg bg-[#C5A059]/10 border border-[#C5A059]/20 flex-shrink-0">
                    <item.icon className="w-5 h-5 text-[#C5A059]" strokeWidth={1.5} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <h3 className="text-white font-semibold tracking-tight">
                        {item.title}
                      </h3>
                      <span className="text-[10px] uppercase tracking-widest text-[#525252] px-2 py-0.5 rounded bg-white/5 border border-white/5">
                        Soon
                      </span>
                    </div>
                    <p className="text-sm text-[#A3A3A3] leading-relaxed">
                      {item.description}
                    </p>

                    {/* Shimmer placeholder rows */}
                    <div className="mt-4 space-y-2">
                      <div className="skeleton-block h-2.5 rounded w-3/4" />
                      <div className="skeleton-block h-2.5 rounded w-1/2" />
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Footer hint */}
          <p className="mt-10 text-center text-xs text-[#525252] tracking-wide">
            Want a setting fast-tracked? Ping the team in #sales-tools.
          </p>
        </motion.div>
    </motion.div>
  );
};

export default SettingsPage;
