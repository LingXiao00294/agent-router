<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useConfigStore } from "@/stores/config";
import type { LogLevel } from "@/api/types";

const store = useConfigStore();
const { draft, fieldErrors } = storeToRefs(store);
</script>

<template>
  <section v-if="draft" class="panel form">
    <h2 class="panel-title">Server</h2>
    <div class="grid">
      <div class="field">
        <label>host</label>
        <input v-model="draft.server.host" />
        <span v-if="fieldErrors['server.host']" class="err">{{ fieldErrors["server.host"] }}</span>
      </div>
      <div class="field">
        <label>port</label>
        <input v-model.number="draft.server.port" type="number" min="1" max="65535" />
        <span v-if="fieldErrors['server.port']" class="err">{{ fieldErrors["server.port"] }}</span>
      </div>
      <div class="field">
        <label>log_level</label>
        <select v-model="draft.server.log_level">
          <option v-for="lv in (['debug','info','warning','error'] as LogLevel[])" :key="lv" :value="lv">
            {{ lv }}
          </option>
        </select>
      </div>
      <div class="field">
        <label>log_file（空=仅 stdout）</label>
        <input v-model="draft.server.log_file" />
      </div>
      <div class="field">
        <label>log_max_bytes</label>
        <input v-model.number="draft.server.log_max_bytes" type="number" min="0" />
      </div>
      <div class="field">
        <label>log_backup_count</label>
        <input v-model.number="draft.server.log_backup_count" type="number" min="0" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.form {
  padding: 1.1rem;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  margin-top: 1rem;
}
.err {
  color: var(--danger);
  font-size: 0.78rem;
}
@media (max-width: 720px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
