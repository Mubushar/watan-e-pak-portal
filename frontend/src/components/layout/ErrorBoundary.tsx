import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

/** Keeps a crashing page from blanking the whole app; reset by changing `resetKey` (the route). */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page crashed:", error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="container flex min-h-[50vh] flex-col items-center justify-center gap-4 py-16 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 text-red-600 dark:bg-red-500/10">
          <AlertTriangle className="h-7 w-7" />
        </span>
        <h2 className="font-display text-2xl font-bold">This screen hit a snag</h2>
        <p className="max-w-md text-sm text-ink-mute">{this.state.error.message}</p>
        <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>
          <RotateCcw className="h-4 w-4" /> Try again
        </button>
      </div>
    );
  }
}
