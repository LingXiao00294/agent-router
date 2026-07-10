<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useConfigStore } from "@/stores/config";

const store = useConfigStore();
const { draft, fieldErrors } = storeToRefs(store);
</script>

<template>
  <section v-if="draft" class="panel form">
    <h2 class="panel-title">Router</h2>
    <p class="muted note">
      页内改 mode 仅标记 dirty，需点保存；顶栏 Mode 会立即 PUT。
    </p>
    <div class="grid">
      <div class="field">
        <label>mode</label>
        <select v-model="draft.router.mode">
          <option value="failover">failover</option>
          <option value="sticky">sticky</option>
        </select>
      </div>
      <div class="field">
        <label>failure_threshold</label>
        <input v-model.number="draft.router.failure_threshold" type="number" min="0" />
        <span v-if="fieldErrors['router.failure_threshold']" class="err">
          {{ fieldErrors["router.failure_threshold"] }}
        </span>
      </div>
      <div class="field">
        <label>recovery_timeout（秒）</label>
        <input v-model.number="draft.router.recovery_timeout" type="number" min="1" />
        <span v-if="fieldErrors['router.recovery_timeout']" class="err">
          {{ fieldErrors["router.recovery_timeout"] }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.form { padding: 1.1rem; }
.note { margin: 0.5rem 0 0; font-size: 0.85rem; }
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
  margin-top: 1rem;
}
.err { color: var(--danger); font-size: 0.78rem; }
@media (max-width: 800px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
