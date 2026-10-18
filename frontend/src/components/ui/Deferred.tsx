import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Render `children` only once the placeholder comes near the viewport, so heavy widgets
 * further down a page (maps, charts) don't load their libraries on first paint.
 */
export function Deferred({ children, height, margin = "400px", className }: { children: ReactNode; height: number | string; margin?: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [show, setShow] = useState(typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (show || !ref.current) return;
    const io = new IntersectionObserver((es) => es.some((e) => e.isIntersecting) && setShow(true), { rootMargin: margin });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [show, margin]);
  if (show) return <>{children}</>;
  return <div ref={ref} className={className} style={{ height }} aria-hidden />;
}
