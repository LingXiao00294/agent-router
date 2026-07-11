import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "overview",
      component: () => import("@/views/Overview.vue"),
    },
    {
      path: "/calls",
      name: "calls",
      component: () => import("@/views/Calls.vue"),
    },
    {
      path: "/config",
      component: () => import("@/views/config/ConfigLayout.vue"),
      children: [
        { path: "", redirect: "/config/models" },
        {
          path: "server",
          name: "config-server",
          component: () => import("@/views/config/ConfigServer.vue"),
        },
        {
          path: "router",
          name: "config-router",
          component: () => import("@/views/config/ConfigRouter.vue"),
        },
        {
          path: "providers",
          name: "config-providers",
          component: () => import("@/views/config/ConfigProviders.vue"),
        },
        {
          path: "models",
          name: "config-models",
          component: () => import("@/views/config/ConfigModels.vue"),
        },
        {
          path: "circuit",
          name: "config-circuit",
          component: () => import("@/views/config/ConfigCircuit.vue"),
        },
      ],
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFound.vue"),
    },
  ],
});

export default router;
