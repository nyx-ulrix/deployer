import { createContext, useContext } from "react";

export type ToastTone = "success" | "error" | "info";

export type ToastItem = { id: number; tone: ToastTone; message: string; title?: string };

export type ToastApi = {
  show: (tone: ToastTone, message: string, title?: string) => void;
  success: (message: string, title?: string) => void;
  error: (message: string, title?: string) => void;
  info: (message: string, title?: string) => void;
};

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
