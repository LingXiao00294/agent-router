import { inject, provide, ref, type InjectionKey, type Ref } from "vue";

interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  danger?: boolean;
}

interface ConfirmState extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

interface ConfirmApi {
  state: Ref<ConfirmState | null>;
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
  answer: (ok: boolean) => void;
}

const KEY: InjectionKey<ConfirmApi> = Symbol("confirm");

export function provideConfirm(): ConfirmApi {
  const state = ref<ConfirmState | null>(null);

  function answer(ok: boolean) {
    state.value?.resolve(ok);
    state.value = null;
  }

  function confirm(opts: ConfirmOptions): Promise<boolean> {
    return new Promise((resolve) => {
      state.value = { ...opts, resolve };
    });
  }

  const api: ConfirmApi = { state, confirm, answer };
  provide(KEY, api);
  return api;
}

export function useConfirm(): ConfirmApi {
  const api = inject(KEY);
  if (!api) throw new Error("Confirm not provided");
  return api;
}
