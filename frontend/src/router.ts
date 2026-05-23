// frontend/src/router.ts

import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
} from "vue-router";

const routes: readonly RouteRecordRaw[] = [
  {
    path: "/",
    name: "index",
    component: () => import("@/views/HomeView.vue"),
  },
];

const router = createRouter({ history: createWebHistory(), routes });

export default router;
