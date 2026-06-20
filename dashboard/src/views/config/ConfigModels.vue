<template>
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

<script setup lang="ts">
import { useConfigStore } from "../../stores/config";
import ConfigSection from "../../components/ConfigSection.vue";
import ModelCard from "../../components/ModelCard.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiEmpty from "../../components/ui/UiEmpty.vue";

const configStore = useConfigStore();

function touch(_path: string) {
  configStore.validate();
}

function onMoveRef(entry: typeof configStore.modelEntries[number], from: number, to: number) {
  configStore.moveRef(entry, from, to);
}
</script>
