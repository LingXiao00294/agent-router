<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { useConfigStore } from "@/stores/config";
import { useConfirm } from "@/composables/useConfirm";
import { useOverlayChrome } from "@/composables/useOverlayChrome";
import type { ProviderConfig, ProviderType } from "@/api/types";
import { isBlankOrPlaceholderKey } from "@/utils/configPayload";

const store = useConfigStore();
const confirm = useConfirm();
const { draft, fieldErrors } = storeToRefs(store);
const newName = ref("");
const editing = ref<string | null>(null);
const modalRef = ref<HTMLElement | null>(null);

const providerEntries = computed(() => {
  if (!draft.value) return [] as { name: string; p: ProviderConfig }[];
  return Object.entries(draft.value.providers).map(([name, p]) => ({ name, p }));
});

const editingProvider = computed(() => {
  if (!editing.value || !draft.value) return null;
  return draft.value.providers[editing.value] ?? null;
});

const modalOpen = computed(() => Boolean(editing.value && editingProvider.value));
useOverlayChrome(modalOpen, modalRef);

watch(newName, (value) => {
  if (fieldErrors.value.providers !== "名称已存在") return;
  const name = value.trim();
  if (name && draft.value?.providers[name]) return;
  const { providers: _nameError, ...remainingErrors } = fieldErrors.value;
  void _nameError;
  fieldErrors.value = remainingErrors;
});

function add() {
  const name = newName.value.trim();
  if (!name) return;
  store.addProvider(name);
  if (draft.value?.providers[name]) {
    newName.value = "";
    editing.value = name;
  }
}

function openEdit(name: string) {
  editing.value = name;
}

function closeEdit() {
  editing.value = null;
}

async function remove(name: string) {
  const ok = await confirm.confirm({
    title: "删除 Provider",
    message: `确定删除「${name}」？`,
    confirmText: "删除",
    danger: true,
  });
  if (ok) {
    const referencedBy = store.removeProvider(name);
    if (referencedBy.length) {
      fieldErrors.value = {
        ...fieldErrors.value,
        providers: `Provider「${name}」仍被虚拟模型引用：${referencedBy.join("、")}。请先保存引用移除。`,
      };
      return;
    }
    if (editing.value === name) editing.value = null;
  }
}

function shortUrl(url: string) {
  if (!url) return "—";
  try {
    const u = new URL(url);
    return u.host + (u.pathname === "/" ? "" : u.pathname.replace(/\/$/, ""));
  } catch {
    return url.length > 40 ? `${url.slice(0, 40)}…` : url;
  }
}

function hasFieldError(name: string) {
  const prefix = `providers.${name}.`;
  return Object.keys(fieldErrors.value).some((k) => k.startsWith(prefix));
}

function keyLabel(p: ProviderConfig) {
  if (p.has_key) return "已配置";
  if (!isBlankOrPlaceholderKey(p.api_key)) return "已填写";
  return "无 key";
}

function keyOk(p: ProviderConfig) {
  return p.has_key || !isBlankOrPlaceholderKey(p.api_key);
}

function onModalKey(e: KeyboardEvent) {
  if (e.key === "Escape" && editing.value) {
    e.preventDefault();
    closeEdit();
  }
}

onMounted(() => window.addEventListener("keydown", onModalKey));
onUnmounted(() => window.removeEventListener("keydown", onModalKey));
</script>

<template>
  <section v-if="draft" class="wrap">
    <div class="toolbar panel">
      <div class="field grow">
        <label>新建 Provider 名称</label>
        <input v-model="newName" placeholder="例如 zai" @keydown.enter="add" />
      </div>
      <button class="btn btn-primary" type="button" @click="add">添加</button>
    </div>
    <p v-if="fieldErrors.providers" class="err">{{ fieldErrors.providers }}</p>

    <div v-if="!providerEntries.length" class="empty-state panel">暂无 Provider，请先添加</div>
    <div v-else class="panel list">
      <div
        v-for="{ name, p } in providerEntries"
        :key="name"
        class="row"
        :class="{ warn: hasFieldError(name) }"
      >
        <div class="row-main" @click="openEdit(name)">
          <div class="row-title">
            <span class="mono name">{{ name }}</span>
            <span class="badge badge-muted">{{ p.type }}</span>
            <span
              class="badge"
              :class="keyOk(p) ? 'badge-success' : 'badge-warn'"
            >
              {{ keyLabel(p) }}
            </span>
            <span v-if="hasFieldError(name)" class="badge badge-danger">校验</span>
          </div>
          <div class="row-sub mono muted">{{ shortUrl(p.base_url) }}</div>
        </div>
        <div class="row-actions">
          <button class="btn btn-sm" type="button" @click="openEdit(name)">编辑</button>
          <button class="btn btn-sm btn-danger" type="button" @click="remove(name)">删除</button>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="editing && editingProvider"
        class="overlay"
        @click.self="closeEdit"
      >
        <div
          ref="modalRef"
          class="modal panel"
          role="dialog"
          aria-modal="true"
          tabindex="-1"
          :aria-label="`编辑 ${editing}`"
        >
          <header class="modal-head">
            <div>
              <h3>编辑 Provider</h3>
              <p class="mono muted">{{ editing }}</p>
            </div>
            <button class="btn btn-sm" type="button" @click="closeEdit">关闭</button>
          </header>

          <div class="grid">
            <div class="field">
              <label>type</label>
              <select v-model="editingProvider.type">
                <option
                  v-for="t in (['anthropic', 'openai'] as ProviderType[])"
                  :key="t"
                  :value="t"
                >
                  {{ t }}
                </option>
              </select>
            </div>
            <div class="field">
              <label>api_key（留空保留原值）</label>
              <input
                v-model="editingProvider.api_key"
                :placeholder="editingProvider.has_key ? '•••• 已配置，留空保留' : '必填'"
                autocomplete="off"
              />
              <span v-if="fieldErrors[`providers.${editing}.api_key`]" class="err">
                {{ fieldErrors[`providers.${editing}.api_key`] }}
              </span>
            </div>
            <div class="field span2">
              <label>base_url</label>
              <input v-model="editingProvider.base_url" />
              <span v-if="fieldErrors[`providers.${editing}.base_url`]" class="err">
                {{ fieldErrors[`providers.${editing}.base_url`] }}
              </span>
            </div>
            <div class="field">
              <label>timeout_seconds</label>
              <input v-model.number="editingProvider.timeout_seconds" type="number" min="1" />
              <span v-if="fieldErrors[`providers.${editing}.timeout`]" class="err">
                {{ fieldErrors[`providers.${editing}.timeout`] }}
              </span>
            </div>
            <div class="field">
              <label>failure_threshold（空=全局）</label>
              <input
                :value="editingProvider.failure_threshold ?? ''"
                type="number"
                @input="editingProvider.failure_threshold = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="field">
              <label>recovery_timeout（空=全局）</label>
              <input
                :value="editingProvider.recovery_timeout ?? ''"
                type="number"
                @input="editingProvider.recovery_timeout = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="field">
              <label>max_concurrent（0=不限）</label>
              <input v-model.number="editingProvider.max_concurrent" type="number" min="0" />
              <span v-if="fieldErrors[`providers.${editing}.max_concurrent`]" class="err">
                {{ fieldErrors[`providers.${editing}.max_concurrent`] }}
              </span>
            </div>
            <div class="field">
              <label>max_queue（0=不排队）</label>
              <input v-model.number="editingProvider.max_queue" type="number" min="0" />
              <span v-if="fieldErrors[`providers.${editing}.max_queue`]" class="err">
                {{ fieldErrors[`providers.${editing}.max_queue`] }}
              </span>
            </div>
            <div class="field">
              <label>queue_wait_timeout</label>
              <input v-model.number="editingProvider.queue_wait_timeout" type="number" min="1" />
              <span v-if="fieldErrors[`providers.${editing}.queue_wait_timeout`]" class="err">
                {{ fieldErrors[`providers.${editing}.queue_wait_timeout`] }}
              </span>
            </div>
            <div class="field">
              <label>rate_limit_cooldown</label>
              <input v-model.number="editingProvider.rate_limit_cooldown" type="number" min="1" />
              <span v-if="fieldErrors[`providers.${editing}.rate_limit_cooldown`]" class="err">
                {{ fieldErrors[`providers.${editing}.rate_limit_cooldown`] }}
              </span>
            </div>
          </div>

          <footer class="modal-foot">
            <button class="btn btn-danger" type="button" @click="remove(editing!)">删除</button>
            <button class="btn btn-primary" type="button" @click="closeEdit">完成</button>
          </footer>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.wrap {
  display: grid;
  gap: 0.75rem;
}

.toolbar {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
}

.grow {
  flex: 1;
}

.list {
  padding: 0;
  overflow: hidden;
}

.row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.9rem;
  border-bottom: 1px solid var(--border);
}

.row:last-child {
  border-bottom: none;
}

.row.warn {
  background: var(--danger-soft);
}

.row-main {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.row-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.name {
  font-weight: 600;
  font-size: 0.95rem;
}

.row-sub {
  margin-top: 0.2rem;
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-actions {
  display: flex;
  gap: 0.35rem;
  flex-shrink: 0;
}

.err {
  color: var(--danger);
  font-size: 0.78rem;
}

.overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  background: rgba(10, 14, 20, 0.45);
  padding: 1rem;
}

.modal {
  width: min(640px, 100%);
  max-height: min(90vh, 820px);
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
  animation: modal-in 0.18s ease;
}

@keyframes modal-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem 1.1rem;
  border-bottom: 1px solid var(--border);
}

.modal-head h3 {
  margin: 0;
  font-size: 1.05rem;
}

.modal-head p {
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  padding: 1rem 1.1rem;
  overflow: auto;
}

.span2 {
  grid-column: span 2;
}

.modal-foot {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.85rem 1.1rem;
  border-top: 1px solid var(--border);
}

@media (max-width: 640px) {
  .row {
    flex-direction: column;
    align-items: stretch;
  }
  .row-actions {
    justify-content: flex-end;
  }
  .grid,
  .span2 {
    grid-template-columns: 1fr;
    grid-column: auto;
  }
}
</style>
