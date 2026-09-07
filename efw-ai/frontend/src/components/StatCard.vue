<template>
  <div class="stat-card">
    <div class="label">{{ label }}</div>
    <div class="value">{{ value }} <span v-if="sub" class="sub">{{ sub }}</span></div>
  </div>
</template>
<script setup>
defineProps({ label: String, value: [String, Number], sub: String, tone: String })
</script>
<style scoped>
.stat-card { flex: 1 1 150px; min-width: 0; background: var(--card);
  border: 1px solid var(--border); border-radius: 12px; padding: 14px; box-sizing: border-box; }
.label { font-size: 12px; color: var(--muted); } .value { font-size: 22px; font-weight: 700; margin-top: 4px; }
.sub { font-size: 12px; color: var(--muted); font-weight: 400; }
</style>
