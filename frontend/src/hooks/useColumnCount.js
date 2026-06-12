import { useState, useEffect } from "react";

export function useColumnCount() {
  const [columnCount, setColumnCount] = useState(() => {
    if (typeof window === "undefined") return 1;
    if (window.innerWidth >= 1280) return 3;
    if (window.innerWidth >= 768) return 2;
    return 1;
  });

  useEffect(() => {
    const update = () => {
      if (window.innerWidth >= 1280) setColumnCount(3);
      else if (window.innerWidth >= 768) setColumnCount(2);
      else setColumnCount(1);
    };
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return columnCount;
}
