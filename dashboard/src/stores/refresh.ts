import { ref, watch } from "vue";
import { defineStore } from "pinia";
import { useLocalStorage, useDocumentVisibility } from "@vueuse/core";

export type RefreshInterval = 0 | 5 | 10 | 30 | 60;

export const useRefreshStore = defineStore("refresh", () => {
  const interval = useLocalStorage<RefreshInterval>("ar-refresh-interval", 10);
  const tick = ref(0);
  const visibility = useDocumentVisibility();
  let timer: ReturnType<typeof setInterval> | null = null;

  function clear() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function restart() {
    clear();
    if (interval.value <= 0) return;
    if (visibility.value === "hidden") return;
    timer = setInterval(() => {
      tick.value += 1;
    }, interval.value * 1000);
  }

  function setIntervalSec(sec: RefreshInterval) {
    interval.value = sec;
    restart();
  }

  function bump() {
    tick.value += 1;
  }

  watch([interval, visibility], () => restart(), { immediate: true });

  return { interval, tick, setIntervalSec, bump, restart };
});
