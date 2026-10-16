import { AnimatePresence, motion } from "framer-motion";
import { Bot, Maximize2, X } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { usePrefs } from "@/store/prefs";
import { ChatPanel } from "./ChatPanel";

/** Floating AI assistant available on every public page. */
export function AssistantWidget() {
  const open = usePrefs((s) => s.assistantOpen);
  const setOpen = usePrefs((s) => s.setAssistantOpen);
  const { pathname } = useLocation();
  if (pathname.startsWith("/ai")) return null;
  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
            className="card fixed bottom-24 end-4 z-[90] flex h-[min(620px,calc(100vh-8rem))] w-[calc(100vw-2rem)] max-w-[420px] flex-col overflow-hidden sm:end-6"
          >
            <div className="flex items-center gap-3 bg-brand-gradient px-4 py-3 text-white">
              <span className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-white/15">
                <Bot className="h-5 w-5" />
                <span className="absolute -end-0.5 -top-0.5 h-3 w-3 rounded-full bg-emerald-400 ring-2 ring-brand-800" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-display font-semibold">AI Property Assistant</p>
                <p className="text-xs text-white/70">RAG over live listings · MCP-powered agents</p>
              </div>
              <Link to="/ai" onClick={() => setOpen(false)} className="btn btn-ghost btn-icon h-9 w-9 text-white hover:bg-white/10" aria-label="Open AI Hub">
                <Maximize2 className="h-4 w-4" />
              </Link>
              <button onClick={() => setOpen(false)} className="btn btn-ghost btn-icon h-9 w-9 text-white hover:bg-white/10" aria-label="Close">
                <X className="h-5 w-5" />
              </button>
            </div>
            <ChatPanel compact className="min-h-0 flex-1" />
          </motion.div>
        )}
      </AnimatePresence>
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 end-4 z-[90] flex h-14 items-center gap-2 rounded-full bg-gold-gradient pe-5 ps-4 font-semibold text-brand-950 shadow-glow transition hover:scale-105 sm:end-6"
        aria-label="Ask AI"
      >
        <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-brand-800 text-white">
          <span className="absolute inset-0 animate-ping rounded-full bg-brand-600 opacity-40" />
          {open ? <X className="relative h-4 w-4" /> : <Bot className="relative h-4 w-4" />}
        </span>
        <span className="hidden sm:inline">{open ? "Close" : "Ask AI"}</span>
      </button>
    </>
  );
}
