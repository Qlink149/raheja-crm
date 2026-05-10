import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, User, Building2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

// Authorised users. Passwords kept simple for this internal tool.
const USERS = {
  ravinder: { password: "rustomjee@123", name: "Ravinder", initials: "R" },
  kishore: { password: "rustomjee@123", name: "Kishore", initials: "K" },
  elton: { password: "rustomjee@123", name: "Elton", initials: "E" },
  tejal: { password: "rustomjee@123", name: "Tejal", initials: "T" },
};

const LoginPage = ({ onLogin }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [showAnimation, setShowAnimation] = useState(false);
  const [username, setUsername] = useState("ravinder");
  const [password, setPassword] = useState("rustomjee@123");
  const [welcomeName, setWelcomeName] = useState("Ravinder");

  const handleSubmit = (e) => {
    e.preventDefault();
    const key = username.trim().toLowerCase();
    const account = USERS[key];
    if (!account || account.password !== password) {
      toast.error("Invalid username or password");
      return;
    }
    setWelcomeName(account.name);
    setIsLoading(true);
    setShowAnimation(true);

    setTimeout(() => {
      onLogin({
        username: key,
        name: account.name,
        initials: account.initials,
      });
    }, 3000);
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#0A0A0A]">
      {/* Background Image with Skyline */}
      <motion.div
        className="absolute inset-0 z-0"
        initial={{ scale: 1.1, y: "10%" }}
        animate={showAnimation ? { scale: 1.3, y: "-20%" } : { scale: 1, y: 0 }}
        transition={{ duration: 3, ease: "easeInOut" }}
      >
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1920&q=80')`,
          }}
        />
        <div className="absolute inset-0 bg-black/70" />
      </motion.div>

      {/* Animated Gold Lines */}
      <div className="absolute inset-0 z-10 pointer-events-none overflow-hidden">
        <motion.div
          className="absolute top-0 left-1/4 w-px h-full bg-gradient-to-b from-transparent via-[#C5A059]/30 to-transparent"
          animate={{ y: ["-100%", "100%"] }}
          transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute top-0 right-1/3 w-px h-full bg-gradient-to-b from-transparent via-[#C5A059]/20 to-transparent"
          animate={{ y: ["100%", "-100%"] }}
          transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
        />
      </div>

      {/* Main Content */}
      <AnimatePresence mode="wait">
        {!showAnimation ? (
          <motion.div
            key="login-form"
            className="relative z-20 flex items-center justify-center min-h-screen px-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -50 }}
            transition={{ duration: 0.5 }}
          >
            <motion.div
              className="w-full max-w-md"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.3 }}
            >
              {/* Logo Section */}
              <div className="text-center mb-12">
                <motion.div
                  className="inline-flex items-center justify-center mb-6"
                  whileHover={{ scale: 1.05 }}
                  transition={{ duration: 0.3 }}
                >
                  <img 
                    src="https://customer-assets.emergentagent.com/job_rustomjee-sales-hub/artifacts/qap04r7n_Rustomjee_logo-removebg-preview.png" 
                    alt="Rustomjee" 
                    className="h-20 w-auto invert"
                  />
                </motion.div>
                <p className="text-[#C5A059] text-sm tracking-[0.3em] uppercase font-medium">
                  Sales Intelligence
                </p>
              </div>

              {/* Login Card */}
              <motion.div
                className="glass-card rounded-lg p-8"
                whileHover={{ borderColor: "rgba(197, 160, 89, 0.4)" }}
              >
                <h2 className="font-serif text-2xl text-white text-center mb-2">
                  Welcome Back
                </h2>
                <p className="text-[#A3A3A3] text-sm text-center mb-8">
                  Access your command center
                </p>

                <form onSubmit={handleSubmit} className="space-y-6">
                  <div className="space-y-2">
                    <label className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold">
                      Username
                    </label>
                    <div className="relative">
                      <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                      <Input
                        data-testid="login-username-input"
                        type="text"
                        placeholder="Enter your username"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="pl-12 bg-black/20 border-white/10 text-white placeholder:text-white/30 focus:border-[#C5A059] focus:ring-1 focus:ring-[#C5A059] rounded-sm h-12"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs uppercase tracking-widest text-[#C5A059] font-semibold">
                      Password
                    </label>
                    <div className="relative">
                      <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                      <Input
                        data-testid="login-password-input"
                        type="password"
                        placeholder="Enter your password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="pl-12 bg-black/20 border-white/10 text-white placeholder:text-white/30 focus:border-[#C5A059] focus:ring-1 focus:ring-[#C5A059] rounded-sm h-12"
                      />
                    </div>
                  </div>

                  <Button
                    data-testid="login-submit-btn"
                    type="submit"
                    disabled={isLoading}
                    className="w-full bg-[#C5A059] text-black hover:bg-[#E5C585] font-semibold rounded-sm h-12 transition-all duration-300 hover:shadow-[0_0_15px_rgba(197,160,89,0.3)]"
                  >
                    {isLoading ? (
                      <span className="flex items-center gap-2">
                        <div className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full spinner" />
                        Entering...
                      </span>
                    ) : (
                      "Enter Command Center"
                    )}
                  </Button>
                </form>

                <p className="text-center text-[#525252] text-xs mt-6">
                  Rustomjee Group &copy; 2026
                </p>
              </motion.div>
            </motion.div>
          </motion.div>
        ) : (
          <motion.div
            key="animation"
            className="relative z-20 flex items-center justify-center min-h-screen"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
          >
            {/* Skyline Rising Animation */}
            <div className="text-center">
              <motion.div
                className="mb-8"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
              >
                <Building2 className="w-16 h-16 text-[#C5A059] mx-auto mb-4" strokeWidth={1} />
              </motion.div>
              
              <motion.h2
                className="font-serif text-3xl text-white mb-4"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
              >
                Welcome, {welcomeName}
              </motion.h2>
              
              <motion.div
                className="flex items-center justify-center gap-2"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6 }}
              >
                <div className="w-2 h-2 rounded-full bg-[#C5A059] animate-pulse" />
                <p className="text-[#A3A3A3] text-sm">
                  Initializing Command Center...
                </p>
              </motion.div>

              {/* Progress Bar */}
              <motion.div
                className="mt-8 w-64 mx-auto h-1 bg-[#1A1A1A] rounded-full overflow-hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.8 }}
              >
                <motion.div
                  className="h-full bg-gradient-to-r from-[#C5A059] to-[#E5C585]"
                  initial={{ width: 0 }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 2, delay: 0.8, ease: "easeInOut" }}
                />
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default LoginPage;
