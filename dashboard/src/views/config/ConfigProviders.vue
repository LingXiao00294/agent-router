<template>
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
</template>

<script setup lang="ts">
import { useConfigStore } from "../../stores/config";
import { useConfirm } from "../../composables/useConfirm";
import ConfigSection from "../../components/ConfigSection.vue";
import ProviderCard from "../../components/ProviderCard.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiEmpty from "../../components/ui/UiEmpty.vue";

const configStore = useConfigStore();
const { confirm } = useConfirm();

function touch(_path: string) {
  configStore.validate();
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
</script>
