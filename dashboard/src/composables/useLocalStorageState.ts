import { ref, watch, type Ref } from "vue";

export function useLocalStorageState<T>(
  key: string,
  defaultValue: T,
  options: { serialize?: (v: T) => string; deserialize?: (s: string) => T } = {}
): Ref<T> {
  const { serialize = JSON.stringify, deserialize = JSON.parse } = options;

  function read(): T {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return defaultValue;
      return deserialize(raw);
    } catch {
      return defaultValue;
    }
  }

  const state = ref<T>(read()) as Ref<T>;

  watch(
    state,
    (value) => {
      try {
        localStorage.setItem(key, serialize(value));
      } catch {
        // ignore storage errors
      }
    },
    { deep: true }
  );

  return state;
}
