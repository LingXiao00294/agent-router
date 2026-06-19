import { ref } from "vue";

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "danger" | "primary";
}

interface ConfirmState extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

export const activeConfirm = ref<ConfirmState | null>(null);

export function confirm(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    activeConfirm.value = {
      title: options.title || "请确认",
      message: options.message,
      confirmText: options.confirmText || "确认",
      cancelText: options.cancelText || "取消",
      variant: options.variant || "primary",
      resolve,
    };
  });
}

export function resolveConfirm(result: boolean) {
  if (activeConfirm.value) {
    activeConfirm.value.resolve(result);
    activeConfirm.value = null;
  }
}

export function useConfirm() {
  return { confirm };
}
