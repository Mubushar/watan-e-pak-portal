import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

function useEsc(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", h);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  useEsc(open, onClose);
  const width = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-3xl", xl: "max-w-5xl" }[size];
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[100] flex items-end justify-center p-0 sm:items-center sm:p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-brand-950/50 backdrop-blur-sm" onClick={onClose} />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ y: 40, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 30, opacity: 0 }}
            transition={{ type: "spring", bounce: 0.15, duration: 0.4 }}
            className={cn("card relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-b-none sm:rounded-2xl", width)}
          >
            {(title || subtitle) && (
              <div className="flex items-start justify-between gap-4 border-b border-black/5 px-6 py-4 dark:border-white/10">
                <div>
                  {title && <h2 className="font-display text-lg font-semibold">{title}</h2>}
                  {subtitle && <p className="text-sm text-ink-mute">{subtitle}</p>}
                </div>
                <button onClick={onClose} className="btn btn-ghost btn-icon -me-2 h-9 w-9" aria-label="Close">
                  <X className="h-5 w-5" />
                </button>
              </div>
            )}
            <div className="overflow-y-auto px-6 py-5">{children}</div>
            {footer && <div className="flex justify-end gap-2 border-t border-black/5 bg-black/[.02] px-6 py-3 dark:border-white/10">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

export function Drawer({
  open,
  onClose,
  title,
  children,
  side = "right",
  width = "max-w-md",
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  side?: "left" | "right";
  width?: string;
}) {
  useEsc(open, onClose);
  // `side` is logical: "right" means the inline end, so drawers mirror in RTL.
  const rtl = typeof document !== "undefined" && document.documentElement.dir === "rtl";
  const atRight = (side === "right") !== rtl;
  const from = atRight ? "100%" : "-100%";
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[100]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-brand-950/40 backdrop-blur-sm" onClick={onClose} />
          <motion.aside
            initial={{ x: from }}
            animate={{ x: 0 }}
            exit={{ x: from }}
            transition={{ type: "spring", bounce: 0, duration: 0.35 }}
            className={cn("absolute top-0 flex h-full w-full flex-col bg-white shadow-2xl dark:bg-[#0b1a12]", width, atRight ? "right-0" : "left-0")}
          >
            <div className="flex items-center justify-between border-b border-black/5 px-5 py-4 dark:border-white/10">
              <div className="font-display text-lg font-semibold">{title}</div>
              <button onClick={onClose} className="btn btn-ghost btn-icon h-9 w-9" aria-label="Close">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">{children}</div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
