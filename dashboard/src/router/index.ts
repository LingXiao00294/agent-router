import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "dashboard",
      meta: { title: "仪表盘" },
      component: () => import("../views/Dashboard.vue"),
    },
    {
      path: "/config",
      component: () => import("../views/config/ConfigLayout.vue"),
      meta: { title: "配置管理" },
      redirect: "/config/server",
      children: [
        {
          path: "server",
          name: "config-server",
          meta: {
            title: "Server",
            subtitle: "服务监听地址与日志配置",
          },
          component: () => import("../views/config/ConfigServer.vue"),
        },
        {
          path: "router",
          name: "config-router",
          meta: {
            title: "Router",
            subtitle: "全局熔断与恢复策略",
          },
          component: () => import("../views/config/ConfigRouter.vue"),
        },
        {
          path: "circuit-breaker",
          name: "config-circuit-breaker",
          meta: {
            title: "熔断器",
            subtitle: "查看与重置各 provider 熔断状态",
          },
          component: () => import("../views/config/ConfigCircuitBreaker.vue"),
        },
        {
          path: "providers",
          name: "config-providers",
          meta: {
            title: "Providers",
            subtitle: "管理上游 API 提供商",
          },
          component: () => import("../views/config/ConfigProviders.vue"),
        },
        {
          path: "models",
          name: "config-models",
          meta: {
            title: "虚拟模型",
            subtitle: "配置虚拟模型与 provider 链",
          },
          component: () => import("../views/config/ConfigModels.vue"),
        },
      ],
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      meta: { title: "页面未找到" },
      component: () => import("../views/NotFound.vue"),
    },
  ],
  scrollBehavior() {
    return { top: 0 };
  },
});

router.beforeEach((to) => {
  const leaf = [...to.matched].reverse().find((record) => record.meta.title);
  const title = leaf?.meta.title;
  document.title = title ? `${String(title)} - Agent Router` : "Agent Router";
});

export default router;
