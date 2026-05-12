import { motion } from "framer-motion";

/**
 * PageTransition — wraps a page's main content with a subtle entrance.
 * Uses opacity + slight Y-translate; keeps everything GPU-accelerated.
 */
const PageTransition = ({ children, className = "" }) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -4 }}
    transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    className={className}
  >
    {children}
  </motion.div>
);

export default PageTransition;
