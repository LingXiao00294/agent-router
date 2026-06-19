<template>
  <div class="config-page">
    <PageHeader title="配置管理" subtitle="管理 providers、虚拟模型与熔断策略">
      <template #actions>
        <UiButton
          variant="primary"
          :loading="configStore.saving"
          :disabled="!configStore.isDirty"
          @click="save"
        >
          保存配置
        </UiButton>
      </template>
    </PageHeader>

    <UiErrorBanner
      v-if="configStore.error"
      :message="configStore.error"
      retry
      class="global-error"
      @retry="configStore.loadConfig"
    />

    <div v-if="configStore.loading" class="loading-wrap">
      <UiSpinner size="lg" />
      <p class="text-muted">加载配置中...</p>
    </div>

    <template v-else>
      <ConfigSection title="Server">
        <div class="form-grid">
          <UiInput v-model="configStore.serverConfig.host" label="Host" />
          <UiInput
            v-model.number="configStore.serverConfig.port"
            label="端口"
            type="number"
            :error="configStore.fieldError('server.port')"
            @blur="touch('server.port')"
          />
          <UiSelect
            v-model="configStore.serverConfig.log_level"
            label="日志级别"
            :options="['debug', 'info', 'warning', 'error']"
          />
          <UiInput
            v-model="configStore.serverConfig.log_file"
            label="日志文件"
            hint="留空则只输出到 stdout"
          />
          <UiInput
            v-model.number="configStore.serverConfig.log_max_bytes"
            label="日志大小限制（字节）"
            type="number"
          />
          <UiInput
            v-model.number="configStore.serverConfig.log_backup_count"
            label="日志备份数"
            type="number"
          />
        </div>
      </ConfigSection>

      <ConfigSection title="Router">
        <div class="form-grid">
          <UiInput
            v-model.number="configStore.routerConfig.failure_threshold"
            label="熔断阈值（次连续失败）"
            type="number"
            :error="configStore.fieldError('router.failure_threshold')"
            @blur="touch('router.failure_threshold')"
          />
          <UiInput
            v-model.number="configStore.routerConfig.recovery_timeout"
            label="恢复超时（秒）"
            type="number"
            :error="configStore.fieldError('router.recovery_timeout')"
            @blur="touch('router.recovery_timeout')"
          />
        </div>
      </ConfigSection>

      <CircuitBreakerPanel
        :states="configStore.circuitStates"
        :loading="false"
        @refresh="configStore.loadCircuitStates"
        @reset="resetCircuit"
      />

      <ConfigSection title="Providers">
        <template #actions>
          <UiButton size="sm" variant="secondary" @click="configStore.addProvider">
            + 添加 Provider
          </UiButton>
        </template>

        <UiEmpty
          v-if="configStore.providerEntries.length === 0"
          title="暂无 provider"
          description="添加第一个 provider 以启用路由"
        />

        <ProviderCard
          v-for="(p, idx) in configStore.providerEntries"
          :key="p.id"
          :entry="p"
          :name-error="configStore.fieldError(`providers[${idx}].name`)"
          :timeout-error="configStore.fieldError(`providers[${idx}].timeout_seconds`)"
          @remove="confirmRemoveProvider(idx)"
          @touch-name="touch(`providers[${idx}].name`)"
          @touch-timeout="touch(`providers[${idx}].timeout_seconds`)"
        />
      </ConfigSection>

      <ConfigSection title="虚拟模型">
        <template #actions>
          <UiButton size="sm" variant="secondary" @click="configStore.addModel">
            + 添加模型
          </UiButton>
        </template>

        <UiEmpty
          v-if="configStore.modelEntries.length === 0"
          title="暂无虚拟模型"
          description="添加虚拟模型并配置 provider 链"
        />

        <ModelCard
          v-for="(m, idx) in configStore.modelEntries"
          :key="m.id"
          :entry="m"
          :provider-names="configStore.providerNames"
          :name-error="configStore.fieldError(`models[${idx}].name`)"
          :refs-error="configStore.fieldError(`models[${idx}].refs`)"
          :provider-errors="m.refs.map((_, ri) => configStore.fieldError(`models[${idx}].refs[${ri}].provider`))"
          :model-errors="m.refs.map((_, ri) => configStore.fieldError(`models[${idx}].refs[${ri}].model`))"
          @remove="configStore.removeModel(idx)"
          @add-ref="configStore.addRef(m)"
          @remove-ref="configStore.removeRef(m, $event)"
          @move-ref="(from, to) => onMoveRef(m, from, to)"
          @touch-name="touch(`models[${idx}].name`)"
          @touch-provider="touch(`models[${idx}].refs[${$event}].provider`)"
          @touch-model="touch(`models[${idx}].refs[${$event}].model`)"
        />
      </ConfigSection>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { useConfigStore } from "../stores/config";
import { useConfirm } from "../composables/useConfirm";
import { useToast } from "../composables/useToast";
import PageHeader from "../components/PageHeader.vue";
import ConfigSection from "../components/ConfigSection.vue";
import ProviderCard from "../components/ProviderCard.vue";
import ModelCard from "../components/ModelCard.vue";
import CircuitBreakerPanel from "../components/CircuitBreakerPanel.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiInput from "../components/ui/UiInput.vue";
import UiSelect from "../components/ui/UiSelect.vue";
import UiEmpty from "../components/ui/UiEmpty.vue";
import UiSpinner from "../components/ui/UiSpinner.vue";
import UiErrorBanner from "../components/ui/UiErrorBanner.vue";

const configStore = useConfigStore();
const { confirm } = useConfirm();
const toast = useToast();

function touch(_path: string) {
  configStore.validate();
}

function onMoveRef(entry: typeof configStore.modelEntries[number], from: number, to: number) {
  configStore.moveRef(entry, from, to);
}

async function save() {
  try {
    const ok = await configStore.saveConfig();
    if (ok) {
      toast.success("配置已保存并热重载");
    }
  } catch {
    toast.error(configStore.error || "保存失败");
  }
}

async function confirmRemoveProvider(idx: number) {
  const p = configStore.providerEntries[idx];
  const refsCount = configStore.modelEntries.reduce(
    (sum, m) => sum + m.refs.filter((r) => r.provider === p?.name).length,
    0
  );
  const msg = refsCount
    ? `删除 ${p?.name || "该 provider"} 会同时移除 ${refsCount} 个模型引用，是否继续？`
    : `确定删除 ${p?.name || "该 provider"} 吗？`;
  const ok = await confirm({
    title: "删除 Provider",
    message: msg,
    confirmText: "删除",
    variant: "danger",
  });
  if (ok) configStore.removeProvider(idx);
}

async function resetCircuit(provider: string) {
  try {
    await configStore.handleResetCircuitBreaker(provider);
    toast.success(`已重置 ${provider} 的熔断状态`);
  } catch {
    toast.error("重置失败");
  }
}

function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (!configStore.saving) save();
  }
}

onBeforeRouteLeave(async (_to, _from, next) => {
  if (!configStore.isDirty) return next();
  const ok = await confirm({
    title: "未保存的更改",
    message: "配置已修改但未保存，确定离开吗？",
    confirmText: "离开",
    cancelText: "留下",
  });
  next(ok);
});

onMounted(() => {
  configStore.loadConfig();
  document.addEventListener("keydown", onKeydown);
});

onUnmounted(() => {
  document.removeEventListener("keydown", onKeydown);
});
</script>

<style scoped>
.config-page {
  padding: 0 var(--space-1);
}
.global-error {
  margin-bottom: var(--space-4);
}
.loading-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-8) 0;
  color: var(--color-text-muted);
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
}
</style>
