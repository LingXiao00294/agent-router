import { inject, provide, ref, type InjectionKey, type Ref } from "vue";

export type ToastKind = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  toasts: Ref<ToastItem[]>;
  push: (message: string, kind?: ToastKind) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  dismiss: (id: number) => void;
}

const KEY: InjectionKey<ToastApi> = Symbol("toast");

let seq = 0;

export function provideToast(): ToastApi {
  const toasts = ref<ToastItem[]>([]);

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }

  function push(message: string, kind: ToastKind = "info") {
    const id = ++seq;
    toasts.value = [...toasts.value, { id, kind, message }];
    window.setTimeout(() => dismiss(id), 4200);
  }

  const api: ToastApi = {
    toasts,
    push,
    success: (m) => push(m, "success"),
    error: (m) => push(m, "error"),
    dismiss,
  };
  provide(KEY, api);
  return api;
}

export function useToast(): ToastApi {
  const api = inject(KEY);
  if (!api) throw new Error("Toast not provided");
  return api;
}
