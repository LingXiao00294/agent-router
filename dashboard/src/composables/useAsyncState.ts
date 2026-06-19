import { ref, type Ref } from "vue";
import { ApiError } from "../api/request";

export interface AsyncState<T, Args extends unknown[] = unknown[]> {
  data: Ref<T | null>;
  loading: Ref<boolean>;
  error: Ref<string | null>;
  execute: (...args: Args) => Promise<T | null>;
  reset: () => void;
}

export function useAsyncState<T, Args extends unknown[] = unknown[]>(
  fn: (...args: Args) => Promise<T>,
  options: { immediate?: boolean; defaultValue?: T; resetOnExecute?: boolean } = {}
): AsyncState<T, Args> {
  const { immediate = false, defaultValue = null, resetOnExecute = false } = options;
  const data = ref<T | null>(defaultValue) as Ref<T | null>;
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function execute(...args: Args): Promise<T | null> {
    loading.value = true;
    if (resetOnExecute) error.value = null;

    try {
      const result = await fn(...args);
      data.value = result;
      error.value = null;
      return result;
    } catch (err) {
      if (err instanceof ApiError) {
        error.value = err.detail;
      } else if (err instanceof Error) {
        error.value = err.message;
      } else {
        error.value = "未知错误";
      }
      return null;
    } finally {
      loading.value = false;
    }
  }

  function reset() {
    data.value = defaultValue;
    loading.value = false;
    error.value = null;
  }

  if (immediate) {
    void execute(...([] as unknown as Args));
  }

  return { data, loading, error, execute, reset };
}

export function useManualAsyncState<T, Args extends unknown[] = unknown[]>(
  fn: (...args: Args) => Promise<T>
): AsyncState<T, Args> {
  return useAsyncState(fn, { immediate: false });
}
