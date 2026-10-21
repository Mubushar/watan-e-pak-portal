import { lazy, Suspense, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Maximize2, X } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";
import { useAssistantDock, useWideScreen } from "@/lib/assistantDock";
import { Spinner } from "@/components/ui";

// The chat (and its agent / map code) loads the first time the widget is opened.
const ChatPanel = lazy(() => import("./ChatPanel").then((m) => ({ default: m.ChatPanel })));

function Header({ onClose, onHub }: { onClose: () => void; onHub: () => void }) {
  return (
    <div className="flex shrink-0 items-center gap-3 bg-brand-gradient px-4 py-3 text-white">
      <span className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-white/15">
        <Bot className="h-5 w-5" />
        <span className="absolute -end-0.5 -top-0.5 h-3 w-3 rounded-full bg-emerald-400 ring-2 ring-brand-800" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-display font-semibold">AI Property Assistant</p>
        <p className="truncate text-xs text-white/70">Maps, listings, reports — ask or attach</p>
      </div>
      <Link to="/ai" onClick={onHub} className="btn btn-ghost btn-icon h-9 w-9 text-white hover:bg-white/10" aria-label="Open AI Hub">
        <Maximize2 className="h-4 w-4" />
      </Link>
      <button onClick={onClose} className="btn btn-ghost btn-icon h-9 w-9 text-white hover:bg-white/10" aria-label="Close the assistant">
        <X className="h-5 w-5" />
      </button>
    </div>
  );
}

function Chat({ children }: { children?: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center">
          <Spinner />
        </div>
      }
    >
      <ChatPanel compact className="min-h-0 flex-1" />
      {children}
    </Suspense>
  );
}

/**
 * The AI assistant on every public page. On the Map page of a wide screen it docks beside the map
 * (the map makes room, so no tool, menu or the header is covered); elsewhere it floats bottom-right,
 * always below the header.
 */
export function AssistantWidget() {
  const open = usePrefs((s) => s.assistantOpen);
  const setOpen = usePrefs((s) => s.setAssistantOpen);
  const { pathname } = useLocation();
  const dock = useAssistantDock();
  const wide = useWideScreen();
  if (pathname.startsWith("/ai")) return null;
  const onMap = pathname === "/map";
  const docked = onMap && wide && !!dock;
  const close = () => setOpen(false);

  return (
    <>
      {docked
        ? open &&
          createPortal(
            <div className="flex h-full w-full flex-col overflow-hidden bg-white dark:bg-brand-950">
              <Header onClose={close} onHub={close} />
              <Chat />
            </div>,
            dock,
          )
        : (
          <AnimatePresence>
            {open && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 12 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className={cn(
                  "card fixed end-4 z-[90] flex w-[calc(100vw-2rem)] max-w-[420px] flex-col overflow-hidden sm:end-6",
                  // Below the sticky header (≈110 px) and above the Ask AI button.
                  onMap ? "bottom-20 h-[min(620px,calc(100dvh-13rem))]" : "bottom-24 h-[min(620px,calc(100dvh-14rem))]",
                )}
              >
                <Header onClose={close} onHub={close} />
                <Chat />
              </motion.div>
            )}
          </AnimatePresence>
        )}
      {!(docked && open) && (
        <button
          onClick={() => setOpen(!open)}
          className={cn(
            "fixed z-[90] flex items-center gap-2 rounded-full bg-gold-gradient pe-5 ps-4 font-semibold text-brand-950 shadow-glow transition-transform hover:scale-105",
            // On the map, sit left of the map's zoom buttons (bottom corner) instead of over them.
            onMap ? "bottom-4 end-16 h-12" : "bottom-6 end-4 h-14 sm:end-6",
          )}
          aria-label={open ? "Close the assistant" : "Ask AI"}
          aria-expanded={open}
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-800 text-white">{open ? <X className="h-4 w-4" /> : <Bot className="h-4 w-4" />}</span>
          <span className="hidden sm:inline">{open ? "Close" : "Ask AI"}</span>
        </button>
      )}
    </>
  );
}
