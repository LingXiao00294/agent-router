import { ref, watch, onScopeDispose } from "vue";
import { useDocumentVisibility } from "@vueuse/core";

const DEFAULT_INTERVAL = 10_000;
export const intervals = [5_000, 10_000, 30_000, 60_000];

const enabled = ref(true);
const intervalMs = ref(DEFAULT_INTERVAL);
const lastTick = ref(Date.now());
const callbacks = new Set<() => void | Promise<void>>();
let timer: ReturnType<typeof setInterval> | null = null;
let watchersCount = 0;

function tick() {
  lastTick.value = Date.now();
  callbacks.forEach((cb) => {
    Promise.resolve(cb()).catch(() => {
      // 单个回调失败不应中断其他回调
    });
  });
}

function start() {
  stop();
  if (enabled.value) {
    timer = setInterval(tick, intervalMs.value);
  }
}

function stop() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

function restart() {
  stop();
  start();
}

export function useAutoRefresh() {
  const visibility = useDocumentVisibility();
  watchersCount++;

  watch(visibility, (v) => {
    if (v === "visible") start();
    else stop();
  });

  watch(enabled, restart);
  watch(intervalMs, restart);

  onScopeDispose(() => {
    watchersCount--;
    if (watchersCount <= 0) stop();
  });

  return {
    enabled,
    intervalMs,
    intervals,
    lastTick,
    register: (cb: () => void | Promise<void>) => {
      callbacks.add(cb);
      return () => callbacks.delete(cb);
    },
    setEnabled: (value: boolean) => {
      enabled.value = value;
    },
    setIntervalMs: (value: number) => {
      if (!intervals.includes(value)) return;
      intervalMs.value = value;
    },
    start,
    stop,
    restart,
    tick,
  };
}
