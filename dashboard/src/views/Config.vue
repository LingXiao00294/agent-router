<template>
  <div class="config-page">
    <div class="top-bar">
      <h2>配置管理</h2>
      <button class="save-btn" @click="saveConfig" :disabled="saving">
        {{ saving ? "保存中..." : "保存配置" }}
      </button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else>
      <!-- Server -->
      <section class="section">
        <h3>Server</h3>
        <div class="server-card">
          <label>Host <input v-model="serverConfig.host" placeholder="127.0.0.1" class="input" /></label>
          <label>端口 <input v-model.number="serverConfig.port" type="number" class="input short" /></label>
          <label>日志级别
            <select v-model="serverConfig.log_level" class="input">
              <option value="debug">debug</option>
              <option value="info">info</option>
              <option value="warning">warning</option>
              <option value="error">error</option>
            </select>
          </label>
        </div>
      </section>

      <!-- Providers -->
      <section class="section">
        <div class="section-header">
          <h3>Providers</h3>
          <button class="add-btn" @click="addProvider">+ 添加</button>
        </div>
        <div v-if="providerEntries.length === 0" class="empty">暂无 provider</div>
        <div v-for="(p, idx) in providerEntries" :key="idx" class="card">
          <div class="card-header">
            <input v-model="p.name" placeholder="provider 名称" class="input name-input" />
            <button class="del-btn" @click="removeProvider(idx)">删除</button>
          </div>
          <div class="card-body">
            <label>类型 <select v-model="p.type" class="input"><option value="anthropic">anthropic</option><option value="openai">openai</option></select></label>
            <label>API Key <input v-model="p.api_key" type="password" placeholder="sk-..." class="input" /></label>
            <label>Base URL <input v-model="p.base_url" placeholder="https://api.anthropic.com" class="input" /></label>
            <label>超时 <input v-model.number="p.timeout_seconds" type="number" class="input short" /> 秒</label>
          </div>
        </div>
      </section>

      <!-- Models -->
      <section class="section">
        <div class="section-header">
          <h3>虚拟模型</h3>
          <button class="add-btn" @click="addModel">+ 添加</button>
        </div>
        <div v-if="modelEntries.length === 0" class="empty">暂无模型</div>
        <div v-for="(m, mi) in modelEntries" :key="mi" class="card">
          <div class="card-header">
            <input v-model="m.name" placeholder="虚拟模型名" class="input name-input" />
            <button class="del-btn" @click="removeModel(mi)">删除</button>
          </div>
          <div class="card-body">
            <div class="section-header">
              <span class="subtitle">Provider 链 (按 priority 排序)</span>
              <button class="add-btn small" @click="addRef(m)">+ 添加 Provider</button>
            </div>
            <div
              v-for="(ref, ri) in m.refs" :key="ri"
              class="ref-row"
              draggable="true"
              @dragstart="onDragStart($event, m, ri)"
              @dragover.prevent="onDragOver($event)"
              @drop="onDrop($event, m, ri)"
              @dragend="onDragEnd"
            >
              <span class="drag-handle" title="拖动排序">⋮⋮</span>
              <span class="priority-badge">{{ ri + 1 }}</span>
              <select v-model="ref.provider" class="input">
                <option value="">选择 provider</option>
                <option v-for="pn in providerNames" :key="pn" :value="pn">{{ pn }}</option>
              </select>
              <input v-model="ref.model" placeholder="真实模型名" class="input flex-1" />
              <button class="del-btn small" @click="removeRef(m, ri)">×</button>
            </div>
          </div>
        </div>
      </section>

      <div v-if="message" class="toast" :class="messageType">{{ message }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

const loading = ref(true);
const saving = ref(false);
const message = ref("");
const messageType = ref("success");

const serverConfig = ref({ host: "127.0.0.1", port: 9456, log_level: "debug" });

interface ProviderEntry {
  name: string;
  type: string;
  api_key: string;
  base_url: string;
  timeout_seconds: number;
}

interface ModelRef {
  provider: string;
  model: string;
  priority: number;  // 自动按顺序生成，不暴露给用户
}

interface ModelEntry {
  name: string;
  refs: ModelRef[];
}

const providerEntries = ref<ProviderEntry[]>([]);
const modelEntries = ref<ModelEntry[]>([]);

const providerNames = computed(() => providerEntries.value.map((p) => p.name).filter(Boolean));

async function loadConfig() {
  loading.value = true;
  const [providers, models] = await Promise.all([
    fetch("/api/config").then((r) => r.json()),
    fetch("/api/config/models").then((r) => r.json()),
  ]);

  if (providers.server) {
    serverConfig.value = {
      host: providers.server.host || "127.0.0.1",
      port: providers.server.port || 9456,
      log_level: providers.server.log_level || "debug",
    };
  }

  providerEntries.value = Object.entries(providers.providers || {}).map(([name, p]: [string, any]) => ({
    name,
    type: p.type || "anthropic",
    api_key: "",
    base_url: p.base_url || "",
    timeout_seconds: p.timeout_seconds || 120,
  }));

  modelEntries.value = Object.entries(models).map(([name, refs]: [string, any]) => ({
    name,
    refs: (refs || []).map((r: any) => ({
      provider: r.provider || "",
      model: r.model || "",
      priority: r.priority || 99,
    })),
  }));

  loading.value = false;
}

function addProvider() {
  providerEntries.value.push({ name: "", type: "anthropic", api_key: "", base_url: "", timeout_seconds: 120 });
}
function removeProvider(idx: number) {
  providerEntries.value.splice(idx, 1);
}

function addModel() {
  modelEntries.value.push({ name: "", refs: [] });
}
function removeModel(idx: number) {
  modelEntries.value.splice(idx, 1);
}
function addRef(m: ModelEntry) {
  m.refs.push({ provider: "", model: "", priority: m.refs.length + 1 });
}
function removeRef(m: ModelEntry, idx: number) {
  m.refs.splice(idx, 1);
}

// --- 拖拽排序 ---
interface DragInfo { model: ModelEntry; idx: number }
let dragInfo: DragInfo | null = null;
let dragOverEl: HTMLElement | null = null;

function onDragStart(e: DragEvent, model: ModelEntry, idx: number) {
  dragInfo = { model, idx };
  (e.target as HTMLElement)?.classList.add("dragging");
  e.dataTransfer!.effectAllowed = "move";
}
function onDragOver(e: DragEvent) {
  e.dataTransfer!.dropEffect = "move";
  dragOverEl?.classList.remove("drag-over");
  dragOverEl = (e.target as HTMLElement)?.closest(".ref-row");
  dragOverEl?.classList.add("drag-over");
}
function onDrop(_e: DragEvent, targetModel: ModelEntry, targetIdx: number) {
  if (!dragInfo || dragInfo.model !== targetModel) return;
  const refs = targetModel.refs;
  const [item] = refs.splice(dragInfo.idx, 1);
  const actualTarget = dragInfo.idx < targetIdx ? targetIdx - 1 : targetIdx;
  refs.splice(actualTarget, 0, item);
}
function onDragEnd(e: DragEvent) {
  (e.target as HTMLElement)?.classList.remove("dragging");
  dragOverEl?.classList.remove("drag-over");
  dragInfo = null;
  dragOverEl = null;
}

async function saveConfig() {
  saving.value = true;
  message.value = "";

  const body: any = {
    server: { ...serverConfig.value },
    providers: {},
    models: {},
  };

  for (const p of providerEntries.value) {
    if (!p.name.trim()) continue;
    body.providers[p.name] = {
      type: p.type,
      api_key: p.api_key || "${PLACEHOLDER}",
      base_url: p.base_url,
      timeout_seconds: p.timeout_seconds,
    };
  }

  for (const m of modelEntries.value) {
    if (!m.name.trim() || m.refs.length === 0) continue;
    body.models[m.name] = m.refs
      .filter((r) => r.provider && r.model)
      .map((r, i) => ({
        provider: r.provider,
        model: r.model,
        priority: i + 1,
      }));
  }

  try {
    const res = await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (res.ok) {
      message.value = data.message;
      messageType.value = "success";
    } else {
      message.value = data.detail || "保存失败";
      messageType.value = "error";
    }
  } catch (e: any) {
    message.value = e.message;
    messageType.value = "error";
  } finally {
    saving.value = false;
  }
}

onMounted(loadConfig);
</script>

<style scoped>
.config-page { padding: 0 8px; }
.top-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 24px;
}
.top-bar h2 { font-size: 20px; }
.save-btn {
  background: #89b4fa; color: #11111b; border: none;
  padding: 8px 20px; border-radius: 6px; cursor: pointer;
  font-size: 14px; font-weight: 600;
}
.save-btn:disabled { opacity: 0.5; cursor: default; }
.save-btn:not(:disabled):hover { background: #b4d0fb; }
.loading { text-align: center; color: #6c7086; padding: 48px; }
.empty { text-align: center; color: #6c7086; padding: 24px; }
.section { margin-bottom: 28px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { font-size: 16px; }
.subtitle { color: #a6adc8; font-size: 13px; }
.add-btn {
  background: #313244; color: #a6e3a1; border: 1px solid #45475a;
  padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 13px;
}
.add-btn:hover { background: #45475a; }
.add-btn.small { padding: 2px 8px; font-size: 12px; }

.card {
  background: #1e1e2e; border: 1px solid #313244;
  border-radius: 8px; padding: 14px; margin-bottom: 12px;
}
.card-header { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
.server-card {
  background: #1e1e2e; border: 1px solid #313244;
  border-radius: 8px; padding: 14px;
  display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-end;
}
.server-card label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #a6adc8; }
.card-body { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
.card-body label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #a6adc8; }

.input {
  background: #11111b; border: 1px solid #313244; border-radius: 4px;
  padding: 6px 10px; color: #cdd6f4; font-size: 13px;
}
.input:focus { outline: none; border-color: #89b4fa; }
.name-input { width: 200px; }
.short { width: 90px; }

.del-btn {
  background: none; border: 1px solid #f38ba8; color: #f38ba8;
  padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;
}
.del-btn:hover { background: #f38ba8; color: #11111b; }
.del-btn.small { padding: 2px 6px; font-size: 11px; }

.ref-row {
  display: flex; gap: 8px; align-items: center; margin-bottom: 6px;
  width: 100%; cursor: default; transition: background 0.15s;
  padding: 4px; border-radius: 4px;
}
.ref-row.dragging { opacity: 0.4; }
.ref-row.drag-over { background: #313244; }
.drag-handle {
  color: #6c7086; font-size: 16px; cursor: grab; user-select: none;
  letter-spacing: 2px; padding: 0 2px;
}
.drag-handle:hover { color: #a6adc8; }
.drag-handle:active { cursor: grabbing; }
.priority-badge {
  background: #313244; color: #a6adc8; font-size: 11px;
  min-width: 22px; text-align: center; border-radius: 4px; padding: 2px 4px;
}
.flex-1 { flex: 1; }

.toast {
  position: fixed; bottom: 24px; right: 24px;
  padding: 12px 24px; border-radius: 6px; font-size: 14px;
}
.toast.success { background: #a6e3a1; color: #11111b; }
.toast.error { background: #f38ba8; color: #11111b; }
</style>
