import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import ToastStack from "../components/ToastStack";

const MAX_TOASTS = 3;
const TOAST_DURATION_MS = 3000;
const DEDUPE_WINDOW_MS = 2000;

export interface ToastItem {
  id: string;
  message: string;
}

interface ToastContextValue {
  showError: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastCounter = 0;

function nextToastId(): string {
  toastCounter += 1;
  return `toast-${toastCounter}`;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const recentRef = useRef<Map<string, number>>(new Map());

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showError = useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) return;

      const now = Date.now();
      const lastShown = recentRef.current.get(trimmed);
      if (lastShown != null && now - lastShown < DEDUPE_WINDOW_MS) return;
      recentRef.current.set(trimmed, now);

      const id = nextToastId();
      setToasts((prev) => {
        const next = [...prev, { id, message: trimmed }];
        if (next.length <= MAX_TOASTS) return next;
        return next.slice(next.length - MAX_TOASTS);
      });

      window.setTimeout(() => dismissToast(id), TOAST_DURATION_MS);
    },
    [dismissToast]
  );

  const value = useMemo(() => ({ showError }), [showError]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}
