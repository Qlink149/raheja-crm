import { motion } from "framer-motion";

/**
 * EmptyState — luxe empty placeholder for any data-less surface.
 *
 * Props:
 *  - icon: lucide-react component (required)
 *  - title: string
 *  - description: string
 *  - action: optional { label, onClick, variant? } — variant defaults to "primary"
 *  - compact: boolean — smaller vertical footprint for inline use
 */
const EmptyState = ({
  icon: Icon,
  title,
  description,
  action,
  compact = false,
  className = "",
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={`flex flex-col items-center justify-center text-center ${
        compact ? "py-10 px-6" : "py-16 px-8"
      } ${className}`}
    >
      {/* Concentric gold rings */}
      <div className="relative mb-6">
        <div className="absolute inset-0 rounded-full bg-[#C5A059]/5 blur-2xl" />
        <div className="absolute inset-0 -m-3 rounded-full border border-[#C5A059]/10" />
        <div className="absolute inset-0 -m-6 rounded-full border border-[#C5A059]/5" />
        <div className="relative flex items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br from-[#1A1A1A] to-[#0E0E0E] border border-[#C5A059]/20 shadow-[0_0_24px_-4px_rgba(197,160,89,0.25)]">
          {Icon ? (
            <Icon className="w-7 h-7 text-[#C5A059]" strokeWidth={1.4} />
          ) : null}
        </div>
      </div>

      <h3 className="text-white text-base font-semibold tracking-tight mb-1.5">
        {title}
      </h3>
      {description ? (
        <p className="text-[#A3A3A3] text-sm max-w-md leading-relaxed">
          {description}
        </p>
      ) : null}

      {action ? (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-r from-[#C5A059] to-[#B89048] text-black text-sm font-semibold btn-tactile hover:shadow-[0_0_20px_-4px_rgba(197,160,89,0.5)] transition-all duration-300"
        >
          {action.icon ? <action.icon className="w-4 h-4" /> : null}
          {action.label}
        </button>
      ) : null}
    </motion.div>
  );
};

export default EmptyState;
