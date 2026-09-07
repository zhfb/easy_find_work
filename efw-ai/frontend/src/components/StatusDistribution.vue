<template>
  <div class="status-dist">
    <div v-for="row in entries" :key="row.key" class="row">
      <span class="label">{{ row.label }}</span>
      <div class="bar-wrap">
        <div class="bar" :style="{ width: pct(row.value) + '%' }"></div>
      </div>
      <span class="value">{{ row.value }}</span>
    </div>
    <div v-if="!entries.length" class="empty">暂无数据</div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ entries: { type: Array, default: () => [] } })
const maxVal = computed(() => Math.max(1, ...props.entries.map(e => Number(e.value) || 0)))
function pct(v) {
  return Math.round((Number(v) / maxVal.value) * 100)
}
</script>
<style scoped>
.status-dist { display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.label { width: 80px; color: var(--muted); flex-shrink: 0; }
.bar-wrap { flex: 1; height: 8px; background: rgba(0,0,0,0.05); border-radius: 4px; overflow: hidden; }
.bar { height: 100%; background: var(--primary); border-radius: 4px; transition: width .3s; }
.value { width: 32px; text-align: right; font-weight: 600; flex-shrink: 0; }
.empty { color: var(--muted); font-size: 12px; text-align: center; padding: 12px 0; }
</style>
