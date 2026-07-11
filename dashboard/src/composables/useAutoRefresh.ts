import { onScopeDispose } from "vue";
import { useRefreshStore } from "@/stores/refresh";

/**
 * Run `fn` on every refresh tick while this component is mounted.
 *
 * The refresh store already pauses ticks while the document is hidden, so `fn`
 * only fires for a visible page. Registration is tied to the component's setup
 * scope — when the page unmounts, `fn` is removed automatically, so at any
 * moment only the currently mounted page's callbacks are active.
 *
 * A rejected promise from `fn` feeds the global stale-data flag (aggregated in
 * App.vue). Each page decides whether its silent-refresh failure should count
 * (e.g. throw when `store.error` is set after a swallowed refresh).
 */
export function useAutoRefresh(fn: () => void | Promise<void>) {
  const refresh = useRefreshStore();
  onScopeDispose(refresh.register(fn));
}
