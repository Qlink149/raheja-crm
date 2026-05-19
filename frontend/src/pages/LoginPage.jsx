import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { Eye, EyeOff, Building2 } from "lucide-react";

const RUSTOMJEE_LOGO =
  "https://customer-assets.emergentagent.com/job_rustomjee-sales-hub/artifacts/qap04r7n_Rustomjee_logo-removebg-preview.png";

const LoginPage = () => {
  const [email, setEmail] = useState("ravinder@rustomjee.com");
  const [password, setPassword] = useState("rustomjee@123");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [showTransition, setShowTransition] = useState(false);
  const [error, setError] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const me = await login(email, password);
      setShowTransition(true);
      const dest = me?.role === "admin" ? "/dashboard" : "/my-dashboard";
      setTimeout(() => {
        navigate(dest, { replace: true });
      }, 3000);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Invalid credentials");
      toast.error("Login failed. Please check your credentials.");
      setIsLoading(false);
    }
  };

  const handleDemoLogin = async () => {
    setEmail("ravinder@rustomjee.com");
    setPassword("rustomjee@123");
    setIsLoading(true);
    setError("");

    try {
      const me = await login("ravinder@rustomjee.com", "rustomjee@123");
      setShowTransition(true);
      const dest = me?.role === "admin" ? "/dashboard" : "/my-dashboard";
      setTimeout(() => {
        navigate(dest, { replace: true });
      }, 3000);
    } catch (err) {
      setError("Failed to login with demo account");
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen relative overflow-hidden bg-[#0A0A0A]">
      <motion.div
        className="absolute inset-0 z-0"
        initial={{ scale: 1.1, y: 50 }}
        animate={{ scale: 1, y: 0 }}
        transition={{ duration: 2, ease: "easeOut" }}
      >
        <motion.div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1920&q=80')`,
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A]/70 to-transparent" />
      </motion.div>

      <AnimatePresence>
        {showTransition && (
          <motion.div
            className="fixed inset-0 z-50 bg-[#0A0A0A] flex flex-col items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.img
              src={RUSTOMJEE_LOGO}
              alt="Rustomjee"
              className="h-16 mb-8 invert"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            />
            <motion.div className="relative w-full max-w-2xl h-48 overflow-hidden">
              <motion.div
                className="absolute bottom-0 w-full flex justify-center gap-2"
                initial={{ y: 200 }}
                animate={{ y: 0 }}
                transition={{ duration: 1.5, ease: "easeOut", delay: 0.5 }}
              >
                {[...Array(12)].map((_, i) => (
                  <motion.div
                    key={i}
                    className="bg-gradient-to-t from-[#C5A059] to-[#C5A059]/30"
                    style={{
                      width: "30px",
                      height: `${60 + (i % 5) * 28}px`,
                      borderRadius: "4px 4px 0 0",
                    }}
                    initial={{ y: 200 }}
                    animate={{ y: 0 }}
                    transition={{
                      duration: 1.2,
                      ease: "easeOut",
                      delay: 0.5 + i * 0.1,
                    }}
                  />
                ))}
              </motion.div>
            </motion.div>
            <motion.div
              className="mt-8 text-center"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2 }}
            >
              <h1 className="font-serif text-3xl text-[#C5A059]">Welcome to Rustomjee</h1>
              <p className="text-[#A1A1AA] mt-2">Sales Intelligence Dashboard</p>
            </motion.div>
            <motion.div
              className="mt-8 h-1 w-48 bg-[#1A1A1A] rounded-full overflow-hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2 }}
            >
              <motion.div
                className="h-full bg-[#C5A059]"
                initial={{ width: "0%" }}
                animate={{ width: "100%" }}
                transition={{ duration: 1, delay: 2 }}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative z-10 min-h-screen flex items-center justify-center px-4">
        <motion.div
          className="w-full max-w-md"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.5 }}
        >
          <motion.div
            className="flex justify-center mb-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8 }}
          >
            <img
              src={RUSTOMJEE_LOGO}
              alt="Rustomjee"
              className="h-12 invert"
              data-testid="login-logo"
            />
          </motion.div>

          <motion.div
            className="glass-card rounded-lg p-8"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 1 }}
          >
            <div className="text-center mb-8">
              <h1 className="font-serif text-2xl text-[#EDEDED]" data-testid="login-title">
                Sales Intelligence
              </h1>
              <p className="text-[#A1A1AA] text-sm mt-2">Sign in to access your dashboard</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-sm text-[#A1A1AA] mb-2">Email Address</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-12 px-4 bg-black/50 border border-white/20 rounded-md text-white focus:border-[#C5A059] transition-colors"
                  placeholder="ravinder@rustomjee.com"
                  required
                  data-testid="login-email-input"
                />
              </div>

              <div>
                <label className="block text-sm text-[#A1A1AA] mb-2">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-12 px-4 pr-12 bg-black/50 border border-white/20 rounded-md text-white focus:border-[#C5A059] transition-colors"
                    placeholder="Enter your password"
                    required
                    data-testid="login-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-[#A1A1AA] hover:text-white transition-colors"
                    data-testid="toggle-password-btn"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-red-500 text-sm text-center"
                  data-testid="login-error"
                >
                  {error}
                </motion.div>
              )}

              <button
                type="submit"
                disabled={isLoading}
                className="w-full h-12 btn-gold font-medium rounded-none disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="login-submit-btn"
              >
                {isLoading ? "Signing in..." : "Sign In"}
              </button>

              <button
                type="button"
                onClick={handleDemoLogin}
                disabled={isLoading}
                className="w-full h-12 btn-gold-outline font-medium rounded-none disabled:opacity-50"
                data-testid="demo-login-btn"
              >
                <span className="flex items-center justify-center gap-2">
                  <Building2 size={18} />
                  Demo Login as Ravinder
                </span>
              </button>
            </form>

            <p className="text-center text-[#52525B] text-xs mt-8">
              Rustomjee — Sales Hub
            </p>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
};

export default LoginPage;
