import { reactive } from "vue";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
  duration: number;
}

let idCounter = 0;

export const toasts = reactive<ToastItem[]>([]);

export function addToast(message: string, type: ToastType = "info", duration = 3000): void {
  const id = ++idCounter;
  toasts.push({ id, message, type, duration });

  if (duration > 0) {
    setTimeout(() => removeToast(id), duration);
  }
}

export function removeToast(id: number): void {
  const idx = toasts.findIndex((t) => t.id === id);
  if (idx >= 0) toasts.splice(idx, 1);
}

export function useToast() {
  return {
    success: (message: string, duration?: number) => addToast(message, "success", duration),
    error: (message: string, duration?: number) => addToast(message, "error", duration),
    warning: (message: string, duration?: number) => addToast(message, "warning", duration),
    info: (message: string, duration?: number) => addToast(message, "info", duration),
    remove: removeToast,
  };
}
