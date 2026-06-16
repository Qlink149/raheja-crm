import React from "react";
import { motion } from "framer-motion";
import { Lock } from "lucide-react";
import { BRAND } from "../../lib/brandConfig";

const PremiumLockedPage = ({ title = "Premium Feature", description }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center min-h-[50vh] text-center px-6"
    >
      <div className="w-16 h-16 rounded-full bg-[#C5A059]/20 flex items-center justify-center mb-6">
        <Lock className="text-[#C5A059]" size={32} />
      </div>
      <h1 className="font-serif text-3xl text-white mb-2">{title}</h1>
      <p className="text-[#A1A1AA] max-w-md">
        {description || BRAND.supportMessage}
      </p>
    </motion.div>
  );
};

export default PremiumLockedPage;
