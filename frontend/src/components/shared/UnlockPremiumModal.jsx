import React, { useEffect } from "react";
import { Lock, X } from "lucide-react";
import { BRAND } from "../../lib/brandConfig";

const UnlockPremiumModal = ({ open, onOpenChange, title = "Unlock Virtual Customer" }) => {
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/80"
        aria-label="Close dialog"
        onClick={() => onOpenChange(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="unlock-premium-title"
        className="relative w-full max-w-md rounded-lg border border-white/10 bg-[#1A1A1A] p-6 text-white shadow-xl"
      >
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className="absolute right-4 top-4 text-[#A1A1AA] hover:text-white transition-colors"
          aria-label="Close"
        >
          <X size={18} />
        </button>

        <div className="w-12 h-12 rounded-full bg-[#C5A059]/20 flex items-center justify-center mb-4 mx-auto">
          <Lock className="text-[#C5A059]" size={22} />
        </div>
        <h2 id="unlock-premium-title" className="font-serif text-xl text-center mb-2">
          {title}
        </h2>
        <p className="text-[#A1A1AA] text-center text-sm leading-relaxed">
          {BRAND.supportMessage}
        </p>
      </div>
    </div>
  );
};

export default UnlockPremiumModal;
