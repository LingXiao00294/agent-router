export interface ConfigNavItemDef {
  id: string;
  to: string;
  label: string;
}

export const CONFIG_NAV_ITEMS: ConfigNavItemDef[] = [
  { id: "server", to: "/config/server", label: "Server" },
  { id: "router", to: "/config/router", label: "Router" },
  { id: "circuit-breaker", to: "/config/circuit-breaker", label: "熔断器" },
  { id: "providers", to: "/config/providers", label: "Providers" },
  { id: "models", to: "/config/models", label: "虚拟模型" },
];

export const DEFAULT_CONFIG_NAV_ORDER = CONFIG_NAV_ITEMS.map((item) => item.id);

export function resolveConfigNavOrder(stored: string[]): string[] {
  const known = new Set(CONFIG_NAV_ITEMS.map((item) => item.id));
  const order = stored.filter((id) => known.has(id));
  for (const item of CONFIG_NAV_ITEMS) {
    if (!order.includes(item.id)) order.push(item.id);
  }
  return order;
}
