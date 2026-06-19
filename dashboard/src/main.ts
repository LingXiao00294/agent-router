import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAppStore } from "./stores/app";
import "./styles/global.css";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);
app.use(router);

// mount 前应用主题，避免刷新时的主题闪烁（FOUC）
useAppStore(pinia).loadTheme();

app.mount("#app");
