<template>
  <div class="timeline">
    <div v-for="(ev, i) in events" :key="i" class="item">
      <div class="dot" :class="ev.event_type || 'info'"></div>
      <div class="content">
        <div class="msg">{{ ev.detail || ev.message || ev.msg || ev.text }}</div>
        <div class="time">{{ ev.time || ev.created_at || '' }}</div>
      </div>
    </div>
    <div v-if="!events.length" class="empty">暂无事件</div>
  </div>
</template>
<script setup>
defineProps({ events: { type: Array, default: () => [] } })
</script>
<style scoped>
.timeline { display: flex; flex-direction: column; gap: 10px; max-height: 280px; overflow-y: auto; }
.item { display: flex; gap: 10px; align-items: flex-start; }
.dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; background: var(--muted); }
.dot.success { background: var(--success); }
.dot.warning { background: var(--warning); }
.dot.danger { background: var(--danger); }
.dot.info { background: var(--primary); }
.content { flex: 1; min-width: 0; }
.msg { font-size: 13px; color: #333; line-height: 1.4; word-break: break-all; }
.time { font-size: 11px; color: var(--muted); margin-top: 2px; }
.empty { color: var(--muted); font-size: 12px; text-align: center; padding: 12px 0; }
</style>
