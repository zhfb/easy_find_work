<template>
  <div class="task-table">
    <table v-if="tasks.length">
      <thead>
        <tr>
          <th>任务</th>
          <th>状态</th>
          <th>进度</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in tasks" :key="t.id">
          <td class="name">
            <router-link :to="`/tasks/${t.id}`">{{ t.name || t.id }}</router-link>
          </td>
          <td>
            <span class="status" :class="t.status">{{ statusLabel(t.status) }}</span>
          </td>
          <td class="progress">
            {{ t.delivered_count ?? t.delivered ?? 0 }} / {{ t.total_count ?? t.total ?? '-' }}
          </td>
          <td class="actions">
            <button v-if="canStart(t.status)" @click="$emit('action', t.id, 'start')">启动</button>
            <button v-if="canPause(t.status)" @click="$emit('action', t.id, 'pause')">暂停</button>
            <button v-if="canResume(t.status)" @click="$emit('action', t.id, 'resume')">继续</button>
            <button v-if="canResumeCrash(t.status)" @click="$emit('action', t.id, 'resume-after-crash')">崩溃续跑</button>
            <button v-if="canStop(t.status)" class="danger" @click="$emit('action', t.id, 'stop')">停止</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">暂无任务，去配置页新建一个</div>
  </div>
</template>
<script setup>
defineProps({ tasks: { type: Array, default: () => [] } })
defineEmits(['action'])

const STATUS_MAP = {
  idle: '空闲', running: '运行中', paused: '已暂停',
  finished: '已完成', stopped: '已停止', failed: '已崩溃',
}
function statusLabel(s) { return STATUS_MAP[s] || s }
function canStart(s) { return s === 'idle' || s === 'finished' || s === 'stopped' }
function canPause(s) { return s === 'running' }
function canResume(s) { return s === 'paused' }
function canResumeCrash(s) { return s === 'failed' }
function canStop(s) { return s === 'running' || s === 'paused' || s === 'failed' }
</script>
<style scoped>
.task-table { width: 100%; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 500;
  border-bottom: 1px solid var(--border); font-size: 12px; }
td { padding: 10px; border-bottom: 1px solid rgba(0,0,0,0.04); vertical-align: middle; }
.name a { color: var(--ink); text-decoration: none; font-weight: 500; }
.name a:hover { text-decoration: underline; }
.status { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.status.idle { background: rgba(0,0,0,0.06); color: var(--muted); }
.status.running { background: rgba(26,26,46,0.1); color: var(--primary); }
.status.paused { background: rgba(245,158,11,0.12); color: var(--warning); }
.status.finished { background: rgba(16,185,129,0.12); color: var(--success); }
.status.stopped { background: rgba(0,0,0,0.06); color: var(--muted); }
.status.failed { background: rgba(239,68,68,0.12); color: var(--danger); }
.progress { color: var(--muted); font-size: 12px; white-space: nowrap; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; }
.actions button { padding: 3px 10px; font-size: 12px; border: 1px solid var(--border);
  background: var(--card); border-radius: 6px; cursor: pointer; color: #333; }
.actions button:hover { background: rgba(0,0,0,0.04); }
.actions button.danger { color: var(--danger); border-color: rgba(239,68,68,0.3); }
.actions button.danger:hover { background: rgba(239,68,68,0.06); }
.empty { color: var(--muted); font-size: 13px; text-align: center; padding: 20px 0; }
</style>
