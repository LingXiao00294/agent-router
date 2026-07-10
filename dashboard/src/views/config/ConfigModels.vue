<script setup lang="ts">
import { computed, ref } from "vue";
import { storeToRefs } from "pinia";
import { useConfigStore } from "@/stores/config";
import { useConfirm } from "@/composables/useConfirm";

const store = useConfigStore();
const confirm = useConfirm();
const { draft, models, fieldErrors } = storeToRefs(store);
const newName = ref("");
const sticky = computed(() => draft.value?.router.mode === "sticky");
const providerNames = computed(() => Object.keys(draft.value?.providers ?? {}));

function add() {
  store.addModel(newName.value.trim());
  newName.value = "";
}

async function remove(name: string) {
  const ok = await confirm.confirm({
    title: "删除虚拟模型",
    message: `确定删除「${name}」？`,
    confirmText: "删除",
    danger: true,
  });
  if (ok) store.removeModel(name);
}

function addRef(model: string) {
  const m = models.value[model];
  if (!m) return;
  const provider = providerNames.value[0] || "";
  m.providers.push({ provider, model: "", priority: m.providers.length + 1 });
}

function removeRef(model: string, idx: number) {
  const m = models.value[model];
  if (!m) return;
  m.providers.splice(idx, 1);
}

function setPin(model: string, idx: number) {
  const m = models.value[model];
  if (!m) return;
  const ref = m.providers[idx];
  if (!ref) return;
  m.pinned_provider = ref.provider;
  m.pinned_model = ref.model;
}

function clearPin(model: string) {
  const m = models.value[model];
  if (!m) return;
  m.pinned_provider = null;
  m.pinned_model = null;
}

function isPinned(model: string, idx: number) {
  const m = models.value[model];
  const ref = m?.providers[idx];
  if (!m || !ref) return false;
  return m.pinned_provider === ref.provider && m.pinned_model === ref.model;
}
</script>

<template>
  <section v-if="draft" class="wrap">
    <div class="toolbar panel">
      <div class="field grow">
        <label>新建虚拟模型</label>
        <input v-model="newName" placeholder="例如 opus-router" @keydown.enter="add" />
      </div>
      <button class="btn btn-primary" type="button" @click="add">添加</button>
    </div>

    <article v-for="(m, name) in models" :key="name" class="panel card">
      <header class="card-head">
        <div>
          <h3 class="mono">{{ name }}</h3>
          <p class="muted tiny">
            链顺序 = priority
            <template v-if="sticky"> · sticky 需 pin</template>
            <template v-else> · failover 时 pin UI 可禁用</template>
          </p>
          <p v-if="fieldErrors[`models.${name}`]" class="err">{{ fieldErrors[`models.${name}`] }}</p>
          <p v-if="fieldErrors[`models.${name}.pin`]" class="err">{{ fieldErrors[`models.${name}.pin`] }}</p>
        </div>
        <button class="btn btn-sm btn-danger" type="button" @click="remove(name)">删除</button>
      </header>

      <div v-if="!m.providers.length" class="empty-state">尚无 provider 引用</div>
      <div v-for="(row, idx) in m.providers" :key="idx" class="ref-row">
        <span class="prio mono">#{{ idx + 1 }}</span>
        <select v-model="row.provider">
          <option disabled value="">选择 provider</option>
          <option v-for="pn in providerNames" :key="pn" :value="pn">{{ pn }}</option>
        </select>
        <input v-model="row.model" placeholder="上游模型名" />
        <div class="ref-actions">
          <button class="btn btn-sm" type="button" :disabled="idx === 0" @click="store.moveRef(name, idx, idx - 1)">↑</button>
          <button class="btn btn-sm" type="button" :disabled="idx === m.providers.length - 1" @click="store.moveRef(name, idx, idx + 1)">↓</button>
          <button
            class="btn btn-sm"
            type="button"
            :class="{ 'btn-primary': isPinned(name, idx) }"
            :disabled="!sticky"
            :title="sticky ? '设为 pin' : 'failover 下 pin 无效'"
            @click="setPin(name, idx)"
          >
            Pin
          </button>
          <button class="btn btn-sm btn-danger" type="button" @click="removeRef(name, idx)">×</button>
        </div>
        <p v-if="fieldErrors[`models.${name}.ref.${idx}`]" class="err ref-err">
          {{ fieldErrors[`models.${name}.ref.${idx}`] }}
        </p>
        <p v-if="fieldErrors[`models.${name}.ref.${idx}.model`]" class="err ref-err">
          {{ fieldErrors[`models.${name}.ref.${idx}.model`] }}
        </p>
      </div>

      <div class="card-foot">
        <button class="btn btn-sm" type="button" @click="addRef(name)">添加引用</button>
        <button
          v-if="m.pinned_provider"
          class="btn btn-sm btn-ghost"
          type="button"
          @click="clearPin(name)"
        >
          清除 pin（{{ m.pinned_provider }}/{{ m.pinned_model }}）
        </button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.wrap { display: grid; gap: 0.85rem; }
.toolbar {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  padding: 0.9rem 1rem;
}
.grow { flex: 1; }
.card { padding: 1rem; }
.card-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.85rem;
}
.card-head h3 { margin: 0; }
.tiny { margin: 0.25rem 0 0; font-size: 0.8rem; }
.ref-row {
  display: grid;
  grid-template-columns: 40px 140px 1fr auto;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.5rem;
}
.ref-err {
  grid-column: 1 / -1;
  margin: 0;
}
.ref-row select,
.ref-row input {
  min-height: 34px;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
}
.prio { color: var(--text-muted); font-size: 0.8rem; }
.ref-actions { display: flex; gap: 0.25rem; }
.card-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.err { color: var(--danger); font-size: 0.78rem; margin: 0.25rem 0 0; }
@media (max-width: 800px) {
  .ref-row {
    grid-template-columns: 1fr;
  }
}
</style>
