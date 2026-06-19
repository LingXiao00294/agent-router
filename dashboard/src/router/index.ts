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
      name: "config",
      meta: { title: "配置管理" },
      component: () => import("../views/Config.vue"),
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
  document.title = to.meta.title ? `${String(to.meta.title)} - Agent Router` : "Agent Router";
});

export default router;
